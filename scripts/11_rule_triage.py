"""Run the rule engine over signals and record its verdicts (D-021 baseline).

Symmetric to `scripts/20_agent_triage.py`, but calls no model: it runs
`core.evidence.build_dossier` directly and costs nothing but archive queries.

    # match an existing agent run's signal set, for a fair side-by-side
    python scripts/11_rule_triage.py --from-run runs/pilot2.json \
        --out runs/rule_pilot2.json

    # the same deterministic pilot sample 20_agent_triage.py uses
    python scripts/11_rule_triage.py --pilot --out runs/rule_pilot.json

**Checks parity is mandatory (D-035).** `20_agent_triage.py` never exposes
instrumental checks to the agent - the TOI queue carries no light curve, so
there is nothing to check. This script wires exactly the same two checks
(`crossmatch_confirmed`, `crossmatch_neighbours`) and nothing else. Adding a
check to one path without adding it to the other would make the comparison
partly measure evidence access instead of judgement.

Makes real archive queries against the NASA Exoplanet Archive and Gaia DR3.
`scripts/30_compare_verdicts.py`, which reads this script's output, does not.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from astro_hunter.core.evidence import build_dossier
from astro_hunter.domains.exoplanets.catalogs import crossmatch_confirmed
from astro_hunter.domains.exoplanets.neighbours import crossmatch_neighbours
from astro_hunter.sources.toi import load_benchmark

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "tests" / "fixtures" / "toi_benchmark.csv"

# Exactly what 20_agent_triage.py exposes to the agent (D-035, see module
# docstring). Keep in sync with astro_hunter.mcp.server's tool registrations.
CHECKS = {
    "confirmed_planets": crossmatch_confirmed,
    "aperture_neighbours": crossmatch_neighbours,
}


def pilot_sample(per_class: int = 2):
    """Two signals per disposition, deterministically chosen - same rule
    `20_agent_triage.py` uses, so `--pilot` on both scripts scores the same
    signals."""
    if not BENCHMARK.exists():
        sys.exit(f"benchmark not found: {BENCHMARK}\nrun scripts/01_build_benchmark.py first")

    by_class = defaultdict(list)
    for signal, label in load_benchmark(BENCHMARK):
        by_class[label].append((signal, label))

    out = []
    for label in sorted(by_class):
        out.extend(by_class[label][:per_class])
    return out


def cases_from_run(run_path: Path):
    """The signal_ids an existing run file scored, resolved back to full
    Signal objects via the pinned benchmark - for a rule run that is
    comparable side by side against that exact agent run."""
    entries = json.loads(run_path.read_text(encoding="utf-8"))
    wanted = {r["signal_id"]: r.get("true_disposition") for r in entries}

    everything = {s.signal_id: (s, label) for s, label in load_benchmark(BENCHMARK)}
    missing = [sid for sid in wanted if sid not in everything]
    if missing:
        sys.exit(
            f"{len(missing)} signal(s) from {run_path} are not in the "
            f"pinned benchmark: {missing[:5]}"
        )

    return [everything[sid] for sid in wanted]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--toi", help="a single signal_id from the benchmark")
    group.add_argument("--pilot", action="store_true", help="two signals per disposition")
    group.add_argument("--from-run", type=Path, help="match an existing run file's signal set")
    group.add_argument("--all", action="store_true", help="the whole pinned benchmark")

    p.add_argument("--per-class", type=int, default=2)
    p.add_argument("--out", type=Path, help="write results as JSON")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.toi:
        everything = load_benchmark(BENCHMARK)
        cases = [(s, label) for s, label in everything if s.signal_id == args.toi]
        if not cases:
            sys.exit(f"{args.toi} not in the benchmark")
    elif args.pilot:
        cases = pilot_sample(args.per_class)
    elif args.from_run:
        cases = cases_from_run(args.from_run)
    else:
        cases = load_benchmark(BENCHMARK)

    results = []
    print(f"{len(cases)} signal(s)\n", flush=True)

    for n, (signal, label) in enumerate(cases, 1):
        dossier = build_dossier(signal, CHECKS)

        record = {
            "signal_id": signal.signal_id,
            "verdict": dossier.verdict.value if dossier.verdict else None,
            "confidence": dossier.confidence,
            "reasoning": dossier.reasoning,
            "stop_reason": "completed",
            "error": None,
            "true_disposition": label,
        }
        results.append(record)

        # Written after every signal, not at the end (same reasoning as
        # 20_agent_triage.py / D-029): a run that stops halfway must not
        # lose the queries already paid for in archive time.
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")

        print(
            f"  {n:>3}/{len(cases)}  {signal.signal_id:>14}  "
            f"truth={label:<4} rule={record['verdict']}",
            flush=True,
        )

    if args.out:
        print(f"\nwrote {args.out}")
        print("compare against the agent with scripts/30_compare_verdicts.py")


if __name__ == "__main__":
    main()
