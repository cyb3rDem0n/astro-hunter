"""Populate the disk cache with light curves for the 54-signal rule-engine
baseline (D-021), and report which targets actually have 2-minute cadence.

    python scripts/01_cache_baseline_lightcurves.py

For every TIC in `runs/rule_baseline.json` (resolved against the pinned
benchmark, `tests/fixtures/toi_benchmark.csv`), asks MAST what TESS light
curve products actually exist for it. A TOI seen only in the full-frame
images has no SPOC 2-minute product - QLP, TESS-SPOC and the other FFI
pipelines run on full-frame cutouts, not on the mission's own short-cadence
pixel stamps - and photometric checks built on that cadence cannot run for
it. That target is still counted, not skipped: the report is exactly this
split, so a later photometric check knows in advance which of the 54 it can
reach.

For every target that does have a SPOC 2-minute product, the first available
sector is downloaded once and cached on disk (D-040); a second run of this
script re-reads the cache and downloads nothing.

Results are written to `runs/lightcurve_availability.json` after every
target, so a run that stops partway does not lose the archive queries
already paid for (same reasoning as `scripts/11_rule_triage.py`, D-029).
"""

import json
from pathlib import Path

from astro_hunter.domains.exoplanets.photometry.tess import (
    MastUnavailable,
    download_tess_lightcurve,
    spoc_2min_sectors,
)
from astro_hunter.sources.toi import load_benchmark

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "tests" / "fixtures" / "toi_benchmark.csv"
BASELINE_RUN = ROOT / "runs" / "rule_baseline.json"
REPORT_OUT = ROOT / "runs" / "lightcurve_availability.json"


def baseline_targets() -> list[tuple[str, str]]:
    """(signal_id, target_id) for the 54 signals scored in the D-021 baseline.

    `runs/rule_baseline.json` names the sample; the pinned benchmark is where
    each signal's TIC id actually lives (the baseline run never carried one).
    """
    wanted = {r["signal_id"] for r in json.loads(BASELINE_RUN.read_text(encoding="utf-8"))}
    by_signal_id = {s.signal_id: s for s, _label in load_benchmark(BENCHMARK)}

    missing = wanted - by_signal_id.keys()
    if missing:
        raise SystemExit(
            f"{len(missing)} baseline signal(s) not in the pinned benchmark: {sorted(missing)[:5]}"
        )
    return [(sid, by_signal_id[sid].target_id) for sid in sorted(wanted)]


def main() -> None:
    targets = baseline_targets()
    print(f"{len(targets)} baseline targets\n", flush=True)

    results: list[dict] = []
    for n, (signal_id, target_id) in enumerate(targets, 1):
        record: dict = {"signal_id": signal_id, "target_id": target_id}

        try:
            sectors = spoc_2min_sectors(target_id)
        except MastUnavailable as exc:
            record["available_2min"] = None
            record["error"] = str(exc)
            print(
                f"  {n:>2}/{len(targets)}  {signal_id:<12} {target_id:<16} MAST unavailable: {exc}"
            )
        else:
            if not sectors:
                record["available_2min"] = False
                record["sectors"] = []
                print(
                    f"  {n:>2}/{len(targets)}  {signal_id:<12} {target_id:<16} "
                    f"no 2-minute product (full-frame images only)"
                )
            else:
                record["available_2min"] = True
                record["sectors"] = sectors
                sector = sectors[0]
                try:
                    download_tess_lightcurve(target_id, sector)
                except MastUnavailable as exc:
                    record["cached_sector"] = None
                    record["error"] = str(exc)
                    print(
                        f"  {n:>2}/{len(targets)}  {signal_id:<12} {target_id:<16} "
                        f"2-min sectors {sectors} but download failed: {exc}"
                    )
                else:
                    record["cached_sector"] = sector
                    print(
                        f"  {n:>2}/{len(targets)}  {signal_id:<12} {target_id:<16} "
                        f"cached sector {sector} (of {sectors})"
                    )

        results.append(record)
        REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
        REPORT_OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")

    available = sum(1 for r in results if r.get("available_2min") is True)
    unavailable = sum(1 for r in results if r.get("available_2min") is False)
    unknown = len(results) - available - unavailable

    print(f"\n{available} of {len(results)} baseline targets have a SPOC 2-minute product")
    print(
        f"{unavailable} are full-frame-image only: no 2-minute-cadence photometric check is possible"
    )
    if unknown:
        print(f"{unknown} could not be determined (MAST unavailable)")
    print(f"\nwrote {REPORT_OUT}")


if __name__ == "__main__":
    main()
