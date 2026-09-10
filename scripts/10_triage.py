"""Triage a candidate signal end to end.

    python scripts/10_triage.py --ra 84.29928 --dec -80.464604 \
        --period 6.268227 --depth-ppm 321 --id pi-men-c

A thin wrapper: parses arguments, wires the domain checks into the core
evidence engine, prints the dossier. No logic.
"""

import argparse
import json

from astro_hunter.core.evidence import build_dossier
from astro_hunter.core.models import Signal
from astro_hunter.domains.exoplanets.catalogs import crossmatch_confirmed
from astro_hunter.domains.exoplanets.neighbours import crossmatch_neighbours


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--id", default="unnamed", help="signal identifier")
    p.add_argument("--ra", type=float, required=True, help="degrees, ICRS")
    p.add_argument("--dec", type=float, required=True, help="degrees, ICRS")
    p.add_argument("--period", type=float, default=None, help="days")
    p.add_argument("--epoch", type=float, default=None)
    p.add_argument("--depth-ppm", type=float, default=None)
    p.add_argument("--duration-hours", type=float, default=None)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    signal = Signal(
        signal_id=args.id,
        source="cli",
        ra_deg=args.ra,
        dec_deg=args.dec,
        period_days=args.period,
        epoch=args.epoch,
        depth_ppm=args.depth_ppm,
        duration_hours=args.duration_hours,
    )

    # Instrumental checks need the light curve, which the CLI does not have.
    checks = {
        "confirmed_planets": crossmatch_confirmed,
        "aperture_neighbours": crossmatch_neighbours,
    }

    dossier = build_dossier(signal, checks)

    if args.json:
        print(json.dumps({
            "signal_id": signal.signal_id,
            "verdict": dossier.verdict.value,
            "confidence": dossier.confidence,
            "reasoning": dossier.reasoning,
            "sources": sorted(dossier.sources_consulted),
            "evidence": [
                {"kind": e.kind.value, "source": e.source, "summary": e.summary,
                 "identifier": e.identifier,
                 "separation_arcsec": e.separation_arcsec}
                for e in dossier.evidence
            ],
        }, indent=2))
        return

    print(f"\n{'=' * 72}")
    print(f"  {signal.signal_id}   RA {signal.ra_deg}  Dec {signal.dec_deg}")
    print(f"{'=' * 72}\n")

    print(f"  VERDICT    {dossier.verdict.value.upper()}  "
          f"(confidence {dossier.confidence:.2f}, rule-derived)")
    print(f"  BECAUSE    {dossier.reasoning}")
    print(f"  RESOLVED   {'yes' if dossier.verdict.is_resolved else 'no - stays in queue'}")
    print(f"\n  EVIDENCE   {len(dossier.evidence)} item(s) from "
          f"{len(dossier.sources_consulted)} source(s)\n")

    for e in dossier.evidence:
        sep = f"  [{e.separation_arcsec:g}\"]" if e.separation_arcsec is not None else ""
        print(f"    - {e.summary}{sep}")
        print(f"        source: {e.source}")
    print()


if __name__ == "__main__":
    main()
