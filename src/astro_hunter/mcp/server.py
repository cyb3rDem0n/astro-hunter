"""MCP server exposing the triage checks as tools.

No new logic: every tool wraps a function that already exists and is already
tested. What this adds is an interface an agent can call, and the constraints
that make an agent usable.

**Results are small.** A tool result is paid for in context tokens and read by
a model with no memory of the previous call. Row counts are capped and payloads
are flattened to what a verdict actually needs. The full evidence objects stay
on the Python side.

**Errors are data, not exceptions.** A tool that raises ends the agent loop. A
tool that returns ``{"error": ..., "hint": ...}`` lets the model adapt — widen a
radius, try again, or record that the check could not run.

**No verdict is exposed** (D-023). The rule engine's verdict is the baseline the
agent is measured against, so the agent must not be able to read it. These tools
return evidence; the comparison happens offline.
"""

from __future__ import annotations

from fastmcp import FastMCP

from astro_hunter.core.models import Signal
from astro_hunter.domains.exoplanets import catalogs, neighbours

mcp = FastMCP("astro-hunter")

MAX_ITEMS = 10


def _signal(ra_deg: float, dec_deg: float, **kw) -> Signal:
    return Signal(signal_id=kw.pop("signal_id", "query"), source="mcp",
                  ra_deg=ra_deg, dec_deg=dec_deg, **kw)


def _flatten(evidence, limit: int = MAX_ITEMS) -> list[dict]:
    """Evidence as small dicts. Provenance is kept; bulk payload is not."""
    return [
        {
            "finding": e.summary,
            "source": e.source,
            "identifier": e.identifier,
            "separation_arcsec": e.separation_arcsec,
            "retrieved_at": e.retrieved_at.isoformat(),
        }
        for e in evidence[:limit]
    ]


@mcp.tool
def check_confirmed_planets(
    ra_deg: float,
    dec_deg: float,
    period_days: float | None = None,
    radius_arcsec: float = 5.0,
) -> dict:
    """Check whether a confirmed exoplanet is already catalogued at this position.

    Queries the NASA Exoplanet Archive. Use this FIRST for any signal: most
    candidates are already known, and finding that out costs one query.

    Supply period_days when you have it. Position alone cannot distinguish a
    rediscovery from a new planet in a known system: the tool reports the
    positional match and the period relation separately.

    A period relation of 'harmonic:2' or 'harmonic:0.5' still means the same
    planet — a blind search commonly locks onto twice or half the true period.
    'unrelated' means the star is catalogued but this particular signal is not
    accounted for, which is the more interesting case.
    """
    try:
        planets = catalogs.find_confirmed_planets(ra_deg, dec_deg, radius_arcsec)
    except catalogs.CatalogUnavailable as exc:
        return {"error": str(exc),
                "hint": "the archive is unreachable; this is not evidence of absence"}

    return {
        "source": "NASA Exoplanet Archive / pscomppars",
        "radius_arcsec": radius_arcsec,
        "match_count": len(planets),
        "planets": [
            {
                "planet": p["planet"],
                "host": p["host"],
                "separation_arcsec": p["separation_arcsec"],
                "period_days": p["period_days"],
                "period_relation": catalogs.period_relation(period_days, p["period_days"]),
                "discovery_year": p["discovery_year"],
                "discovery_facility": p["discovery_facility"],
            }
            for p in planets[:MAX_ITEMS]
        ],
    }


@mcp.tool
def check_aperture_contamination(
    ra_deg: float,
    dec_deg: float,
    depth_ppm: float | None = None,
    radius_arcsec: float = 60.0,
) -> dict:
    """Find sources in the photometric aperture that could mimic the signal.

    Queries Gaia DR3. A nearby eclipsing binary whose light falls in the
    aperture is the dominant false-positive mechanism in transit surveys, and it
    is invisible in the light curve alone.

    Supply depth_ppm to get the decisive number. For each neighbour the tool
    reports the deepest dip it could produce if totally eclipsed — its own share
    of the aperture flux. A neighbour whose maximum falls below the observed
    depth is EXCLUDED as the origin: nothing can remove more light than it
    emits. That is an exclusion, not a likelihood.

    'dilution' is the fraction of aperture flux belonging to the target.
    Contaminating light is constant while the target dips, so it fills in the
    transit and every measured depth understates the truth.

    If target_found is false there is no star close enough to the position to be
    the signal's source, and nothing here can be assessed. If
    brighter_neighbours is non-zero the position may have resolved to the wrong
    star.

    This is a screening tool: the aperture is treated as a sharp circle and the
    pixel response function is ignored. Do not report these numbers as
    false-positive probabilities.
    """
    try:
        signal = _signal(ra_deg, dec_deg, depth_ppm=depth_ppm)
        evidence = neighbours.crossmatch_neighbours(signal, radius_arcsec)
    except neighbours.CatalogUnavailable as exc:
        return {"error": str(exc),
                "hint": "Gaia is unreachable; this is not evidence of a clean aperture"}

    summary = evidence[0]
    if summary.payload.get("target_found") is False:
        return {
            "source": "Gaia DR3",
            "target_found": False,
            "finding": summary.summary,
        }

    capable = [
        {
            "source_id": e.identifier,
            "separation_arcsec": e.separation_arcsec,
            "max_producible_depth_ppm": e.payload["max_producible_depth_ppm"],
            "could_explain_signal": e.payload["could_explain_signal"],
        }
        for e in evidence
        if "could_explain_signal" in e.payload
    ]

    return {
        "source": "Gaia DR3",
        "target_found": True,
        "target_source_id": summary.payload.get("target_source_id"),
        "dilution": summary.payload.get("dilution"),
        "neighbour_count": summary.payload.get("neighbour_count"),
        "brighter_neighbours": summary.payload.get("brighter_neighbours", 0),
        "neighbours": capable[:MAX_ITEMS],
        "findings": _flatten(evidence, limit=3),
    }


@mcp.tool
def check_period_relation(candidate_period_days: float, known_period_days: float) -> dict:
    """Compare a candidate period against a known one, allowing for harmonics.

    Use this when a catalogue gives a period in a different form, or to test
    whether a signal is an alias of another. Returns 'match', 'harmonic:<n>',
    or 'unrelated'.
    """
    return {
        "relation": catalogs.period_relation(candidate_period_days, known_period_days),
        "ratio": (candidate_period_days / known_period_days
                  if known_period_days else None),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
