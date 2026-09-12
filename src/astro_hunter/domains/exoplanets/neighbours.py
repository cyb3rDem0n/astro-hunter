"""Contaminating sources in the photometric aperture.

Evidence path for `FP` and `CONTAMINATED` (D-017). A nearby eclipsing binary
whose light falls inside the aperture is the dominant false-positive mechanism
in transit surveys, and it is invisible in the light curve alone.

TESS pixels are about 21 arcsec across, so an aperture of a few pixels admits
every source within roughly a minute of arc. Their combined flux dilutes the
signal, and any one of them, if it eclipses, can masquerade as a shallow
transit on the target.

Two quantities follow from the flux ratios, and they answer different questions:

**Dilution** — how much the measured depth understates the true depth on the
target. Contaminating flux is constant, so it fills in the dip.

**Maximum producible depth** — the deepest dip a given neighbour could ever
cause. A source contributing a fraction r of the aperture flux produces at most
a fraction r when totally eclipsed. If the observed depth exceeds that, this
neighbour is ruled out as the origin, which is a rigorous exclusion rather
than a likelihood.

Scope. This is a screening tool. It treats the aperture as a sharp circle and
ignores the pixel response function, so the flux fractions are approximations
that are useful for ranking and exclusion, not for validation. Statistical
validation of a candidate needs a tool that models the pixel response, such as
TRICERATOPS.

**Partner data centres (D-036).** ESA's own archive is not the only place to
ask: Gaia's CU9 consortium runs official mirrors, and ESA's query engine has
a documented history of multi-hour outages (D-032, D-033). Queries fail over,
in order, from ESA to two partner mirrors, ARI (Heidelberg) and AIP
(Potsdam), each with its own circuit breaker so one archive's outage cannot
be mistaken for another's. Which archive actually answered is recorded as
provenance (D-014) - `find_neighbours` returns it, and `crossmatch_neighbours`
uses it as every emitted `Evidence`'s `source`, because it changes: an ESA
result and an ARI result are the same underlying release queried through
different software, and a claim's source is not an implementation detail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import astropy.units as u
from astropy.coordinates import SkyCoord

from astro_hunter.core.adql import cone_predicate
from astro_hunter.core.http import CircuitBreaker, tap_service
from astro_hunter.core.models import Evidence, EvidenceKind

TAP_URL = "https://gea.esac.esa.int/tap-server/tap"
TABLE = "gaiadr3.gaia_source"

TESS_PIXEL_ARCSEC = 21.0
DEFAULT_APERTURE_ARCSEC = 60.0           # a few TESS pixels
DEFAULT_MAG_LIMIT = 8.0                  # fainter than target + this contributes < 0.1 %
MAX_NEIGHBOURS_REPORTED = 15

# A source must lie this close to the signal position to be the target. Gaia DR3
# contains about 1.8 billion sources, so a 60 arcsec cone finds something almost
# anywhere: without this limit, the nearest source in the aperture gets promoted
# to target however far away and however unrelated it is, and every quantity
# downstream is then computed against the wrong star.
DEFAULT_TARGET_RADIUS_ARCSEC = TESS_PIXEL_ARCSEC / 2


class CatalogUnavailable(RuntimeError):
    """No endpoint answered. Distinct from 'no neighbours found'."""


@dataclass(frozen=True)
class GaiaEndpoint:
    """One Gaia TAP mirror: its own URL, its own table, its own circuit breaker.

    Two mirrors must never share a fate (D-033) - ESA being down says nothing
    about ARI - so each endpoint carries its own `CircuitBreaker` rather than
    a shared one. Schemas are not assumed identical between mirrors either
    (D-036, verified live): `table` is whatever was actually confirmed to
    carry the seven columns this module needs at that specific service.

    `service`, when set, is used as-is instead of `url`/`breaker` - the seam
    tests inject through, and what the legacy `find_neighbours(service=...)`
    parameter becomes internally (a one-element endpoint list).
    """

    name: str
    url: str
    table: str
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    service: object | None = None

    def resolve(self):
        return (
            self.service
            if self.service is not None
            else tap_service(self.url, breaker=self.breaker)
        )


# One breaker per archive, shared by every call in a run against that archive
# (D-032, D-033). Kept as a module-level name distinct from ESA's own breaker
# because `neighbours.BREAKER is not catalogs.BREAKER` is a standing
# regression test for "two archives never share a fate" - it now also holds,
# unchanged, one level down: `ESA.breaker is not ARI.breaker is not AIP.breaker`.
BREAKER = CircuitBreaker()

# Live-verified this session (D-036): ESA's sync endpoint answers /availability
# and /capabilities but its query engine is stalled (D-032, D-033). ARI and AIP
# are official CU9 partner mirrors and, checked directly against each service's
# TAP_SCHEMA.columns, both expose gaiadr3.gaia_source_lite with the seven
# columns below, matching units, right now. A third candidate found in Gaia
# documentation (Observatoire de Paris, gaia.obspm.fr/tap-server/tap) was
# tried and dropped: the URL returns the site's HTML homepage, not a TAP
# response - documentation is not verification.
ESA = GaiaEndpoint(name="Gaia DR3 / ESA", url=TAP_URL, table=TABLE, breaker=BREAKER)
ARI = GaiaEndpoint(
    name="Gaia DR3 / ARI mirror",
    url="https://gaia.ari.uni-heidelberg.de/tap",
    table="gaiadr3.gaia_source_lite",
)
AIP = GaiaEndpoint(
    name="Gaia DR3 / AIP mirror", url="https://gaia.aip.de/tap", table="gaiadr3.gaia_source_lite"
)

DEFAULT_ENDPOINTS: tuple[GaiaEndpoint, ...] = (ESA, ARI, AIP)


def flux_ratio(neighbour_mag: float, target_mag: float) -> float:
    """Flux of a neighbour relative to the target, from their magnitudes.

    The magnitude scale is logarithmic: five magnitudes correspond to a factor
    of 100 in flux, so a source five magnitudes fainter contributes one per
    cent.
    """
    return 10.0 ** (-0.4 * (neighbour_mag - target_mag))


def dilution(flux_ratios: list[float]) -> float:
    """Fraction of aperture flux coming from the target itself.

    1.0 means an uncontaminated aperture. 0.5 means half the light is not the
    target, and every measured depth is understated by a factor of two.
    """
    return 1.0 / (1.0 + sum(flux_ratios))


def corrected_depth(observed_depth: float, flux_ratios: list[float]) -> float:
    """The depth the signal would have on an uncontaminated target.

    Contaminating flux is constant while the target dips, so it fills in the
    transit. Undoing that is a division by the dilution factor - and it is why
    a planet radius derived from a raw depth is systematically too small.
    """
    return observed_depth / dilution(flux_ratios)


def max_depth_from_neighbour(ratio: float, all_ratios: list[float]) -> float:
    """Deepest observed dip this neighbour could produce if totally eclipsed.

    Its own flux, as a fraction of everything in the aperture. Nothing it does
    can remove more light than it emits, which makes this an upper bound rather
    than an estimate.
    """
    return ratio / (1.0 + sum(all_ratios))


def _select_adql(table: str, ra_deg: float, dec_deg: float, radius_arcsec: float) -> str:
    return f"""
        SELECT source_id, ra, dec, phot_g_mean_mag, parallax, pmra, pmdec
        FROM {table}
        WHERE {cone_predicate(ra_deg, dec_deg, radius_arcsec)}
          AND phot_g_mean_mag IS NOT NULL
    """


def _query_endpoints(ra_deg: float, dec_deg: float, radius_arcsec: float, endpoints):
    """Try each endpoint in order; any failure moves to the next (D-036).

    This covers an already-open circuit breaker with no special-casing -
    `CircuitOpen` is just one more `Exception` - as well as a fresh failure
    that has nothing to do with a breaker at all. Only once every endpoint has
    failed is the query itself a failure.

    Returns (rows, endpoint that answered). The endpoint is returned even when
    the archive answered with zero matching rows, since "which archive
    answered" and "how many rows it returned" are independent facts.
    """
    failures = []
    for ep in endpoints:
        adql = _select_adql(ep.table, ra_deg, dec_deg, radius_arcsec)
        try:
            rows = ep.resolve().search(adql).to_table()
        except Exception as exc:  # noqa: BLE001 - any failure tries the next endpoint
            failures.append(f"{ep.name}: {exc}")
            continue
        return rows, ep

    raise CatalogUnavailable(f"every Gaia endpoint failed: {'; '.join(failures)}")


def find_neighbours(
    ra_deg: float,
    dec_deg: float,
    radius_arcsec: float = DEFAULT_APERTURE_ARCSEC,
    mag_limit: float = DEFAULT_MAG_LIMIT,
    target_radius_arcsec: float = DEFAULT_TARGET_RADIUS_ARCSEC,
    service=None,
    endpoints: tuple[GaiaEndpoint, ...] | None = None,
) -> tuple[dict | None, list[dict], str]:
    """Gaia DR3 sources in the aperture, tried across the partner chain (D-036).

    Returns (target, neighbours, gaia_source). The target is the source
    closest to the given position *and* within ``target_radius_arcsec`` of
    it; if nothing is that close, there is no identifiable target and
    (None, [], gaia_source) is returned - ``gaia_source`` is still meaningful,
    since a query can succeed and simply find nothing.

    That radius is not a detail. Gaia sees something almost everywhere, so
    without it a distant unrelated source becomes the target and the dilution,
    the corrected depth and every exclusion are computed against the wrong star.

    ``service``, when given, pins a single service and disables failover -
    what every existing caller passing it explicitly wants (a fixed test
    double, or `tools/measure_gaia_latency.py` measuring one archive on
    purpose). ``endpoints`` overrides the default partner chain directly, for
    tests that need to exercise the failover itself.
    """
    if endpoints is None:
        endpoints = (
            (GaiaEndpoint(name="Gaia DR3", url="", table=TABLE, service=service),)
            if service is not None
            else DEFAULT_ENDPOINTS
        )

    rows, answered_by = _query_endpoints(ra_deg, dec_deg, radius_arcsec, endpoints)
    gaia_source = answered_by.name

    centre = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    found = []
    for r in rows:
        if r["ra"] is None or r["dec"] is None:
            continue
        here = SkyCoord(ra=float(r["ra"]) * u.deg, dec=float(r["dec"]) * u.deg, frame="icrs")
        sep = float(centre.separation(here).arcsec)
        if sep > radius_arcsec:
            continue
        found.append({
            "source_id": str(r["source_id"]),
            "separation_arcsec": round(sep, 3),
            "g_mag": float(r["phot_g_mean_mag"]),
        })

    if not found:
        return None, [], gaia_source

    found.sort(key=lambda s: s["separation_arcsec"])
    if found[0]["separation_arcsec"] > target_radius_arcsec:
        return None, [], gaia_source
    target = found[0]
    neighbours = [
        s for s in found[1:]
        if s["g_mag"] - target["g_mag"] <= mag_limit
    ]

    for n in neighbours:
        n["flux_ratio"] = flux_ratio(n["g_mag"], target["g_mag"])

    neighbours.sort(key=lambda s: s["flux_ratio"], reverse=True)
    return target, neighbours[:MAX_NEIGHBOURS_REPORTED], gaia_source


def crossmatch_neighbours(
    signal,
    radius_arcsec: float = DEFAULT_APERTURE_ARCSEC,
    service=None,
    endpoints: tuple[GaiaEndpoint, ...] | None = None,
) -> list[Evidence]:
    """Aperture contamination as Evidence for a Dossier.

    Every `Evidence.source` below names the archive that actually answered
    (D-014, D-036) rather than a fixed "Gaia DR3" literal - ESA and ARI are
    the same release, but a claim's source is where it came from, not what
    it is about.
    """
    target, neighbours, gaia_source = find_neighbours(
        signal.ra_deg, signal.dec_deg, radius_arcsec, service=service, endpoints=endpoints
    )
    retrieved = datetime.now(UTC)

    if target is None:
        return [Evidence(
            kind=EvidenceKind.NEIGHBOUR,
            source=gaia_source,
            summary=(
                f"no Gaia source within {DEFAULT_TARGET_RADIUS_ARCSEC:g} arcsec of the "
                f"position: the signal cannot be attributed to a star"
            ),
            retrieved_at=retrieved,
            payload={"target_found": False,
                     "target_radius_arcsec": DEFAULT_TARGET_RADIUS_ARCSEC},
        )]

    ratios = [n["flux_ratio"] for n in neighbours]
    d = dilution(ratios)

    brighter = [n for n in neighbours if n["g_mag"] < target["g_mag"]]
    evidence = [Evidence(
        kind=EvidenceKind.NEIGHBOUR,
        source=gaia_source,
        summary=(
            f"{len(neighbours)} contaminating source(s) within {radius_arcsec:g} arcsec; "
            f"target contributes {d:.1%} of aperture flux"
        ),
        retrieved_at=retrieved,
        identifier=target["source_id"],
        payload={
            "target_source_id": target["source_id"],
            "target_g_mag": target["g_mag"],
            "dilution": round(d, 5),
            "neighbour_count": len(neighbours),
            "radius_arcsec": radius_arcsec,
            "target_found": True,
            "brighter_neighbours": len(brighter),
        },
    )]

    if brighter:
        evidence.append(Evidence(
            kind=EvidenceKind.NEIGHBOUR,
            source=gaia_source,
            summary=(
                f"{len(brighter)} source(s) in the aperture are brighter than the "
                f"assumed target: the position may have resolved to the wrong star"
            ),
            retrieved_at=retrieved,
            payload={"brighter_neighbours": len(brighter),
                     "target_g_mag": target["g_mag"],
                     "brightest_neighbour_g_mag": min(n["g_mag"] for n in brighter),
                     "target_identification_doubtful": True},
        ))

    if signal.depth_ppm:
        observed = signal.depth_ppm * 1e-6
        evidence.append(Evidence(
            kind=EvidenceKind.DERIVED,
            source=f"dilution correction ({gaia_source} flux ratios)",
            summary=(
                f"observed depth {signal.depth_ppm:.0f} ppm corresponds to "
                f"{corrected_depth(observed, ratios) * 1e6:.0f} ppm on an "
                f"uncontaminated target"
            ),
            retrieved_at=retrieved,
            payload={
                "observed_depth_ppm": signal.depth_ppm,
                "corrected_depth_ppm": round(corrected_depth(observed, ratios) * 1e6, 1),
                "dilution": round(d, 5),
            },
        ))

        for n in neighbours:
            capacity = max_depth_from_neighbour(n["flux_ratio"], ratios)
            can_explain = capacity >= observed
            evidence.append(Evidence(
                kind=EvidenceKind.NEIGHBOUR,
                source=gaia_source,
                summary=(
                    f"source {n['source_id']} at {n['separation_arcsec']:g} arcsec "
                    f"could produce at most {capacity * 1e6:.0f} ppm: "
                    + ("cannot" if not can_explain else "could")
                    + " account for the signal"
                ),
                retrieved_at=retrieved,
                identifier=n["source_id"],
                separation_arcsec=n["separation_arcsec"],
                payload={
                    **n,
                    "max_producible_depth_ppm": round(capacity * 1e6, 1),
                    "could_explain_signal": can_explain,
                },
            ))

    return evidence
