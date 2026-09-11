"""Download the labelled benchmark sample once and commit it.

    python scripts/01_build_benchmark.py --per-class 100

Writes tests/fixtures/toi_benchmark.csv. Commit the result: evaluations are run
against the pinned file, not the live catalog, so that results stay comparable
as dispositions are revised (D-015).
"""

import argparse
from collections import Counter
from pathlib import Path

from astro_hunter.sources.toi import fetch_benchmark_sample, write_benchmark

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "toi_benchmark.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-class", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260911)
    args = parser.parse_args()

    print(f"querying the TOI catalog (up to {args.per_class} per disposition) ...")
    sample = fetch_benchmark_sample(per_class=args.per_class, seed=args.seed)

    counts = Counter(label for _signal, label in sample)
    for label, n in counts.most_common():
        print(f"  {label:>5}  {n}")

    with_period = sum(1 for s, _ in sample if s.period_days)
    with_depth = sum(1 for s, _ in sample if s.depth_ppm)
    print(f"\n{len(sample)} signals; {with_period} carry a period, {with_depth} a depth")

    write_benchmark(sample, OUT)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    print("commit it: evaluations run against this file, not the live catalog")


if __name__ == "__main__":
    main()
