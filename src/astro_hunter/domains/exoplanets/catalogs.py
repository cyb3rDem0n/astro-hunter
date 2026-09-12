"""Catalog cross-match for the exoplanet domain.

The cheapest and most discriminating check in the system: most candidates are
already catalogued, and finding that out costs one query. It runs first.

Evidence path for `KP` and `CP` (D-016). In benchmark mode the TOI catalog is
withheld, so the confirmed-planet tables are the independent route to
recognising an already-known object.

Positional coincidence alone is not identity. A star that hosts a known planet
can also host an unknown one, and multi-planet systems are exactly where
additional planets are found. A match therefore reports the positional
agreement *and* the period relation separately, so that "known star, unknown
period" stays distinguishable from "known planet".
"""

from __future__ import annotations

from datetime import UTC, datetime

import astropy.units as u
import pyvo
from astropy.coordinates import SkyCoord

from astro_hunter.core.http import CircuitBreaker, tap_service
from astro_hunter.core.models import Evidence, EvidenceKind

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP"

# pscomppars carries one row per planet with a filled-in parameter set, while
# ps carries one row per published reference. For "is a planet already known
# here" the former is the right table; the latter would return duplicates.
TABLE = "pscomppars"

DEFAULT_MATCH_RADIUS_ARCSEC = 5.0
DEFAULT_PERIOD_TOLERANCE = 0.01          # fractional
HARMONIC_RATIOS = (0.25, 1 / 3, 0.5, 1.0, 2.0, 3.0, 4.0)


class CatalogUnavailable(RuntimeError):
    """The archive could not be reached or refused the query.

    Raised rather than swallowed: an empty result and an unreachable service
    mean opposite things, and conflating them would let a network failure be
    read as "nothing known here".
    """


# One breaker for this archive (D-033), so a batch stops paying for an outage it
# has already found. `sources/toi.py` addresses the same host but keeps its own:
# they sit on opposite sides of the source/domain boundary, and sharing one would
# couple them for a saving of at most one wasted request budget per run.
BREAKER = CircuitBreaker()


def _service() -> pyvo.dal.TAPService:
    """A service that times out rather than hanging, and gives up on an outage."""
    return tap_service(TAP_URL, breaker=BREAKER)


def period_relation(
    candidate_days: float | None,
    known_days: float | None,
    tolerance: float = DEFAULT_PERIOD_TOLERANCE,
) -> str:
    """Describe how a candidate period relates to a known one.

    Returns 'match', 'harmonic:<ratio>', 'unrelated', or 'unknown' when either
    period is missing.

    Harmonics matter because a blind search routinely locks onto twice or half
    the true period. A candidate at 2x a known planet's period is the same
    planet, not a new one.
    """
    if not candidate_days or not known_days or known_days <= 0:
        return "unknown"

    ratio = candidate_days / known_days
    for h in HARMONIC_RATIOS:
        if abs(ratio - h) / h <= tolerance:
            return "match" if h == 1.0 else f"harmonic:{h:g}"
    return "unrelated"


def _bounding_box(ra_deg: float, dec_deg: float, radius_arcsec: float):
    """A generous RA/Dec box for the ADQL prefilter.

    Deliberately not CONTAINS/POINT/CIRCLE: support for ADQL geometry varies
    between services and versions, while comparison operators do not. The box
    over-selects; the exact angular separation is then computed with astropy,
    which also handles the RA convergence near the poles correctly.
    """
    radius_deg = radius_arcsec / 3600.0
    dec_min = max(-90.0, dec_deg - radius_deg)
    dec_max = min(90.0, dec_deg + radius_deg)

    # Widen in RA by 1/cos(dec); near the poles fall back to the full range.
    import math

    cos_dec = math.cos(math.radians(min(abs(dec_min), abs(dec_max))))
    if cos_dec < 1e-6:
        return 0.0, 360.0, dec_min, dec_max
    ra_pad = radius_deg / cos_dec
    return ra_deg - ra_pad, ra_deg + ra_pad, dec_min, dec_max


def find_confirmed_planets(
    ra_deg: float,
    dec_deg: float,
    radius_arcsec: float = DEFAULT_MATCH_RADIUS_ARCSEC,
    service=None,
) -> list[dict]:
    """Confirmed planets within a radius of a sky position.

    Returns one dict per planet with name, host, period, radius and the exact
    angular separation in arcseconds. Empty list means nothing catalogued
    there; an unreachable service raises instead.
    """
    ra_min, ra_max, dec_min, dec_max = _bounding_box(ra_deg, dec_deg, radius_arcsec)
    adql = f"""
        SELECT pl_name, hostname, ra, dec, pl_orbper, pl_rade, disc_year, disc_facility
        FROM {TABLE}
        WHERE dec BETWEEN {dec_min} AND {dec_max}
          AND ra BETWEEN {ra_min} AND {ra_max}
    """
    try:
        rows = (service or _service()).search(adql).to_table()
    except Exception as exc:
        raise CatalogUnavailable(f"{TABLE} query failed: {exc}") from exc

    target = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    out = []
    for r in rows:
        if r["ra"] is None or r["dec"] is None:
            continue
        here = SkyCoord(ra=float(r["ra"]) * u.deg, dec=float(r["dec"]) * u.deg, frame="icrs")
        sep = target.separation(here).arcsec
        if sep > radius_arcsec:
            continue
        out.append({
            "planet": str(r["pl_name"]),
            "host": str(r["hostname"]),
            "separation_arcsec": round(float(sep), 3),
            "period_days": None if r["pl_orbper"] is None else float(r["pl_orbper"]),
            "radius_earth": None if r["pl_rade"] is None else float(r["pl_rade"]),
            "discovery_year": None if r["disc_year"] is None else int(r["disc_year"]),
            "discovery_facility": str(r["disc_facility"]),
        })
    return sorted(out, key=lambda p: p["separation_arcsec"])


def crossmatch_confirmed(signal, radius_arcsec: float = DEFAULT_MATCH_RADIUS_ARCSEC,
                         service=None) -> list[Evidence]:
    """Turn a confirmed-planet cross-match into Evidence for a Dossier.

    One Evidence per matched planet. The summary states the positional match
    and the period relation as separate facts, because they support different
    conclusions: a positional match with an unrelated period means a known
    *star* and an unexplained signal, which is more interesting than either
    fact alone.
    """
    planets = find_confirmed_planets(signal.ra_deg, signal.dec_deg, radius_arcsec, service)
    retrieved = datetime.now(UTC)

    if not planets:
        return [Evidence(
            kind=EvidenceKind.CATALOG_MATCH,
            source="NASA Exoplanet Archive / pscomppars",
            summary=f"no confirmed planet within {radius_arcsec:g} arcsec",
            retrieved_at=retrieved,
            payload={"radius_arcsec": radius_arcsec, "matches": 0},
        )]

    evidence = []
    for p in planets:
        relation = period_relation(signal.period_days, p["period_days"])
        summary = (
            f"{p['planet']} at {p['separation_arcsec']:g} arcsec; "
            f"period {relation}"
        )
        evidence.append(Evidence(
            kind=EvidenceKind.CATALOG_MATCH,
            source="NASA Exoplanet Archive / pscomppars",
            summary=summary,
            retrieved_at=retrieved,
            identifier=p["planet"],
            separation_arcsec=p["separation_arcsec"],
            payload={**p, "period_relation": relation},
        ))
    return evidence
