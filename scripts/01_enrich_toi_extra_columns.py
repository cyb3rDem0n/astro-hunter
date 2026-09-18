"""Add st_rad/st_teff/st_logg/pl_rade to the pinned benchmark, in place.

    python scripts/01_enrich_toi_extra_columns.py

Fills tests/fixtures/toi_benchmark.csv's new columns from a live catalog query,
matched back to the already-pinned signal_ids. Deliberately not the same thing
as re-running scripts/01_build_benchmark.py: which signals are pinned, and
their dispositions, are untouched (D-037) - only the four new columns change.
"""

from pathlib import Path

from astro_hunter.sources.toi import enrich_extra_columns

BENCHMARK = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "toi_benchmark.csv"


def main() -> None:
    print(f"enriching {BENCHMARK} from the live TOI catalog ...")
    stats = enrich_extra_columns(BENCHMARK)
    print(f"{stats['matched']}/{stats['total']} rows matched; "
          f"{stats['unmatched']} left blank (signal_id no longer in the catalog)")
    print("dispositions and which signals are pinned are unchanged (D-037)")


if __name__ == "__main__":
    main()
