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
"""

from __future__ import annotations

from datetime import UTC, datetime

import astropy.units as u
import pyvo
from astropy.coordinates import SkyCoord

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
    """The archive could not be reached. Distinct from 'no neighbours found'."""


# One breaker for the Gaia archive, shared by every call in a run. Gaia's query
# engine has been observed stalled for twelve hours at a stretch (D-032); this is
# what stops a batch from paying the full retry budget once per signal to learn
# that again. Module-level because a run is a process, and `_service()` builds a
# fresh service per query — a caller wanting its own can inject one instead.
BREAKER = CircuitBreaker()


def _service() -> pyvo.dal.TAPService:
    """A service that times out rather than hanging, and gives up on an outage."""
    return tap_service(TAP_URL, breaker=BREAKER)


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


def _cone_predicate(ra_deg: float, dec_deg: float, radius_arcsec: float) -> str:
    """ADQL cone prefilter; the exact separation is still computed afterwards.

    This replaces a bounding box on plain ``ra``/``dec`` ranges (D-034). The box
    had a defect that produced no error: an RA interval built by subtraction does
    not wrap, so near RA 0 or 360 it read like ``BETWEEN -0.01 AND 0.01`` and
    matched nothing. Every signal in that strip came back as "no Gaia source at
    this position" — a wrong answer that looks exactly like a real one.

    A cone has no seam to get wrong, and it is the form Gaia's spatial index
    serves. It is not a change of method: the selection is still a prefilter,
    and `find_neighbours` still filters on exact angular separation after it.
    """
    return (
        f"1 = CONTAINS("
        f"POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {ra_deg!r}, {dec_deg!r}, {radius_arcsec / 3600.0!r}))"
    )


def find_neighbours(
    ra_deg: float,
    dec_deg: float,
    radius_arcsec: float = DEFAULT_APERTURE_ARCSEC,
    mag_limit: float = DEFAULT_MAG_LIMIT,
    target_radius_arcsec: float = DEFAULT_TARGET_RADIUS_ARCSEC,
    service=None,
) -> tuple[dict | None, list[dict]]:
    """Gaia DR3 sources in the aperture.

    Returns (target, neighbours). The target is the source closest to the given
    position *and* within ``target_radius_arcsec`` of it; if nothing is that
    close, there is no identifiable target and (None, []) is returned.

    That radius is not a detail. Gaia sees something almost everywhere, so
    without it a distant unrelated source becomes the target and the dilution,
    the corrected depth and every exclusion are computed against the wrong star.
    """
    adql = f"""
        SELECT source_id, ra, dec, phot_g_mean_mag, parallax, pmra, pmdec
        FROM {TABLE}
        WHERE {_cone_predicate(ra_deg, dec_deg, radius_arcsec)}
          AND phot_g_mean_mag IS NOT NULL
    """
    try:
        rows = (service or _service()).search(adql).to_table()
    except Exception as exc:
        raise CatalogUnavailable(f"Gaia query failed: {exc}") from exc

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
        return None, []

    found.sort(key=lambda s: s["separation_arcsec"])
    if found[0]["separation_arcsec"] > target_radius_arcsec:
        return None, []
    target = found[0]
    neighbours = [
        s for s in found[1:]
        if s["g_mag"] - target["g_mag"] <= mag_limit
    ]

    for n in neighbours:
        n["flux_ratio"] = flux_ratio(n["g_mag"], target["g_mag"])

    neighbours.sort(key=lambda s: s["flux_ratio"], reverse=True)
    return target, neighbours[:MAX_NEIGHBOURS_REPORTED]


def crossmatch_neighbours(
    signal,
    radius_arcsec: float = DEFAULT_APERTURE_ARCSEC,
    service=None,
) -> list[Evidence]:
    """Aperture contamination as Evidence for a Dossier."""
    target, neighbours = find_neighbours(
        signal.ra_deg, signal.dec_deg, radius_arcsec, service=service
    )
    retrieved = datetime.now(UTC)

    if target is None:
        return [Evidence(
            kind=EvidenceKind.NEIGHBOUR,
            source="Gaia DR3",
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
        source="Gaia DR3",
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
            source="Gaia DR3",
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
            source="dilution correction (Gaia DR3 flux ratios)",
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
                source="Gaia DR3",
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
