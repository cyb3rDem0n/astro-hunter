"""Compare agent verdicts against the rule-engine baseline (D-013).

    python scripts/30_compare_verdicts.py \
        --agent-run runs/pilot2.json --rule-run runs/rule_pilot2.json

A thin wrapper: reads two already-saved run files and prints the comparison
via `core.metrics`. No network calls, no model calls - everything here
operates on what `scripts/20_agent_triage.py` and `scripts/11_rule_triage.py`
already collected and wrote to disk.
"""

import argparse
import json
from pathlib import Path

from astro_hunter.core.metrics import compare, format_report, record_from_dict


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--agent-run", type=Path, required=True, help="JSON written by scripts/20_agent_triage.py"
    )
    p.add_argument(
        "--rule-run", type=Path, required=True, help="JSON written by scripts/11_rule_triage.py"
    )
    return p.parse_args()


def load_records(path: Path):
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [record_from_dict(entry) for entry in entries]


def main() -> None:
    args = parse_args()
    agent_records = load_records(args.agent_run)
    rule_records = load_records(args.rule_run)
    print(format_report(compare(agent_records, rule_records)))


if __name__ == "__main__":
    main()
