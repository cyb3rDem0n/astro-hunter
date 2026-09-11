"""Run the agent over signals and record what it decided.

This is the only script that spends API credit. Start small.

    # one signal, verbose
    python scripts/20_agent_triage.py --toi TOI-144.01 --verbose

    # the pilot: two per disposition from the pinned benchmark
    python scripts/20_agent_triage.py --pilot --out runs/pilot.json

    # cost estimate without calling the API
    python scripts/20_agent_triage.py --pilot --dry-run

Reads ANTHROPIC_API_KEY from the environment. The key is never written to a
file, which is what keeps it out of the repository.
"""

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from astro_hunter.core.agent import anthropic_tool_schemas, run_agent
from astro_hunter.mcp import server as mcp_server
from astro_hunter.sources.toi import load_benchmark

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "tests" / "fixtures" / "toi_benchmark.csv"

# Published rates per million tokens. Used for reporting only; verify against
# the current pricing page before relying on a total.
PRICING = {
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-5": (15.0, 75.0),
}

TOOL_FUNCTIONS = {
    "check_confirmed_planets": mcp_server.check_confirmed_planets,
    "check_aperture_contamination": mcp_server.check_aperture_contamination,
    "check_period_relation": mcp_server.check_period_relation,
}


def execute_tool(name: str, arguments: dict) -> dict:
    """Run a tool by name. Errors come back as data, never as exceptions."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    return fn(**arguments)


def pilot_sample(per_class: int = 2):
    """A few signals from each disposition, deterministically chosen.

    Stratified so the pilot exercises every verdict path. Taking the first of
    each class rather than sampling keeps repeated runs comparable while the
    prompt is being tuned.
    """
    if not BENCHMARK.exists():
        sys.exit(f"benchmark not found: {BENCHMARK}\n"
                 f"run scripts/01_build_benchmark.py first")

    by_class = defaultdict(list)
    for signal, label in load_benchmark(BENCHMARK):
        by_class[label].append((signal, label))

    out = []
    for label in sorted(by_class):
        out.extend(by_class[label][:per_class])
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--toi", help="a single signal_id from the benchmark")
    group.add_argument("--pilot", action="store_true",
                       help="two signals per disposition")
    group.add_argument("--all", action="store_true",
                       help="the whole benchmark - costs real money")

    p.add_argument("--per-class", type=int, default=2)
    p.add_argument("--model", default="claude-sonnet-5")
    p.add_argument("--max-iterations", type=int, default=8)
    p.add_argument("--out", type=Path, help="write results as JSON")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="list what would run, and estimate cost, without calling")
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
    else:
        cases = load_benchmark(BENCHMARK)

    rate_in, rate_out = PRICING.get(args.model, (3.0, 15.0))

    if args.dry_run:
        print(f"{len(cases)} signal(s), model {args.model}")
        for signal, label in cases:
            print(f"  {signal.signal_id:>14}   disposition {label}")
        # ~9500 in / ~600 out per signal on a three-tool path
        estimate = len(cases) * (9500 / 1e6 * rate_in + 600 / 1e6 * rate_out)
        print(f"\nrough estimate: ${estimate:.2f} "
              f"(assumes ~9500 input and ~600 output tokens per signal)")
        print("no API call made")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set in the environment")

    import anthropic
    client = anthropic.Anthropic()

    schemas = anthropic_tool_schemas(asyncio.run(mcp_server.mcp.list_tools()))

    results, total_cost = [], 0.0

    print(f"{len(cases)} signal(s), model {args.model}\n", flush=True)

    for n, (signal, label) in enumerate(cases, 1):
        run = run_agent(signal, client, schemas, execute_tool,
                        model=args.model, max_iterations=args.max_iterations)

        cost = run.cost_usd(rate_in, rate_out)
        total_cost += cost

        record = asdict(run)
        record["started_at"] = str(run.started_at)
        record["finished_at"] = str(run.finished_at)
        record["true_disposition"] = label
        record["cost_usd"] = round(cost, 5)
        results.append(record)

        # Written after every signal, not at the end: a batch that stops
        # halfway must not lose the runs already paid for.
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")

        status = run.verdict or f"[{run.stop_reason}]"
        print(f"  {n:>3}/{len(cases)}  {signal.signal_id:>14}  "
              f"truth={label:<4} agent={status:<13} "
              f"{run.iterations} turn(s)  ${cost:.4f}", flush=True)

        if args.verbose:
            if run.reasoning:
                print(f"        {run.reasoning}")
            if run.tools_called:
                print(f"        tools: {', '.join(run.tools_called)}")
            if run.error:
                print(f"        error: {run.error}")
            print()

    print(f"\ntotal cost: ${total_cost:.4f}")
    submitted = sum(1 for r in results if r["verdict"])
    print(f"verdicts submitted: {submitted}/{len(results)}")

    if args.out:
        print(f"wrote {args.out}")
        print("compare against the rule baseline with the metrics step")


if __name__ == "__main__":
    main()
