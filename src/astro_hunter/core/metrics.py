"""Evaluation against expert dispositions (D-013).

Compares verdicts - the agent's or the rule engine's (`core.evidence`) - to
dispositions assigned by human experts in the TOI catalog (D-015), and
reports precision, recall and F1 per class plus the macro average, for both
verdict sources side by side.

**Raw accuracy is not reported** (D-015): the classes are heavily
imbalanced, and always answering the majority class alone scores 59.5%
without doing anything. That number is surfaced explicitly, as the baseline
every result is judged against, not hidden behind an accuracy figure.

**`FP` accepts two verdicts** (D-017): an on-target eclipsing binary
(`EXPLAINED`) and a nearby one whose light leaks into the aperture
(`CONTAMINATED`) are both a correct read of a TESS false positive, because
the disposition itself does not distinguish them. Both score as correct for
the `FP` class; the confusion matrix still records which one was produced.

**A run without a verdict is not a classification error.** An archive outage
or an agent that ran out of iterations says nothing about judgement quality.
Those runs are pulled out before scoring and tallied by `stop_reason`.

**Known ceiling, stated rather than left to be inferred from the matrix.**
The rule engine cannot produce `EXPLAINED` (D-021): distinguishing an
on-target eclipsing binary from a nearby one needs odd/even depth and a
secondary-eclipse search, neither implemented. And *neither* path can
produce a grounded `INSTRUMENTAL` verdict here: the TOI queue carries no
light curve, so neither the rule engine nor the agent is given an
instrumental check (D-035) - same reason `scripts/11_rule_triage.py` wires
only the two checks `scripts/20_agent_triage.py` exposes to the agent, and
no more. If a check is ever added to one path, it must be added to both, or
the comparison starts measuring evidence access instead of judgement.

Boundaries: reports numbers, never adjusts thresholds to improve them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from astro_hunter.core.models import Verdict

# --- D-017: disposition -> target class --------------------------------------

# `FP` is not a `Verdict` value: it stands for "either EXPLAINED or
# CONTAMINATED is correct", which no single Verdict expresses.
TRUE_CLASSES: tuple[str, ...] = ("KNOWN", "INSTRUMENTAL", "FP", "INTERESTING", "INSUFFICIENT")

DISPOSITION_TO_CLASS: dict[str, str] = {
    "KP": "KNOWN",
    "CP": "KNOWN",
    "FA": "INSTRUMENTAL",
    "FP": "FP",
    "PC": "INTERESTING",
    "APC": "INSUFFICIENT",
}

FP_ACCEPTED_VERDICTS: frozenset[Verdict] = frozenset({Verdict.EXPLAINED, Verdict.CONTAMINATED})

# The other four classes each accept exactly one verdict.
SINGLE_CLASS_VERDICT: dict[str, Verdict] = {
    "KNOWN": Verdict.KNOWN,
    "INSTRUMENTAL": Verdict.INSTRUMENTAL,
    "INTERESTING": Verdict.INTERESTING,
    "INSUFFICIENT": Verdict.INSUFFICIENT,
}

# --- D-015: pinned TOI snapshot, 2026-09-10 (docs/toi-schema-snapshot.md) ----
# Real catalog proportions, not the stratified sample's - the majority
# baseline must reflect what "always guess the biggest class" actually scores
# against the population being evaluated, not against a deliberately balanced
# sample.

PINNED_SNAPSHOT_COUNTS: dict[str, int] = {
    "PC": 4836,
    "FP": 1290,
    "CP": 815,
    "KP": 607,
    "APC": 486,
    "FA": 100,
}
PINNED_SNAPSHOT_NULL_COUNT = 14  # unlabelled rows; excluded from evaluation


def majority_baseline_share() -> float:
    """Accuracy of always predicting the majority disposition's class.

    Computed on the pinned snapshot's real proportions (D-015), excluding the
    14 null rows the same way scored evaluation does - not on the stratified
    per-class sample, which would understate how skewed the true catalog is.
    """
    labelled = sum(PINNED_SNAPSHOT_COUNTS.values())
    return max(PINNED_SNAPSHOT_COUNTS.values()) / labelled


def majority_baseline_class() -> str:
    """The target class that baseline always guesses."""
    disposition = max(PINNED_SNAPSHOT_COUNTS, key=PINNED_SNAPSHOT_COUNTS.get)
    return DISPOSITION_TO_CLASS[disposition]


# --- input records -------------------------------------------------------------


@dataclass(frozen=True)
class VerdictRecord:
    """One scored signal: the verdict produced, and the truth to check it against.

    Common shape for both paths - an agent run (`runs/pilot2.json`) and a
    rule-engine run (`scripts/11_rule_triage.py`'s output) - so `score` does
    not need to know which produced it.
    """

    signal_id: str
    true_disposition: str | None
    verdict: Verdict | None
    stop_reason: str | None = None


def record_from_dict(d: dict) -> VerdictRecord:
    """Adapt one run-file entry (agent or rule shape; they share field names)."""
    raw_verdict = d.get("verdict")
    return VerdictRecord(
        signal_id=d["signal_id"],
        true_disposition=d.get("true_disposition"),
        verdict=Verdict(raw_verdict) if raw_verdict else None,
        stop_reason=d.get("stop_reason"),
    )


# --- scoring -------------------------------------------------------------------


@dataclass(frozen=True)
class ClassMetrics:
    """Precision, recall and F1 for one class. `None` means undefined here -
    zero predictions of this class, or zero true instances of it - not zero.
    """

    precision: float | None
    recall: float | None
    f1: float | None
    support: int


@dataclass
class Report:
    """One path's scored evaluation."""

    per_class: dict[str, ClassMetrics]
    macro_precision: float | None
    macro_recall: float | None
    macro_f1: float | None
    confusion: dict[str, Counter]  # true class -> Counter[predicted verdict value]
    excluded_null: int  # true_disposition outside the pinned label set
    no_verdict: Counter  # stop_reason -> count, for runs with no verdict
    scored: int  # records that entered the confusion matrix


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or (precision + recall) == 0:
        return None
    return 2 * precision * recall / (precision + recall)


def _macro(values: list[float | None]) -> float | None:
    """Mean of the defined values. A class with no support or no predictions
    contributes nothing to define, rather than being treated as zero - an
    undefined ratio is not the same claim as a bad one.
    """
    defined = [v for v in values if v is not None]
    return sum(defined) / len(defined) if defined else None


def score(records: list[VerdictRecord]) -> Report:
    """Confusion matrix and per-class precision/recall/F1 for one path.

    Splits `records` three ways before scoring anything: a null/unlabelled
    disposition is not a class (D-015) and a missing verdict is not a
    classification error (D-031-adjacent reasoning, applied here) - both are
    counted, neither is scored.
    """
    no_verdict: Counter = Counter()
    excluded_null = 0
    scored_records: list[VerdictRecord] = []

    for r in records:
        if r.true_disposition not in DISPOSITION_TO_CLASS:
            excluded_null += 1
            continue
        if r.verdict is None:
            no_verdict[r.stop_reason or "unknown"] += 1
            continue
        scored_records.append(r)

    confusion: dict[str, Counter] = {cls: Counter() for cls in TRUE_CLASSES}
    for r in scored_records:
        cls = DISPOSITION_TO_CLASS[r.true_disposition]
        confusion[cls][r.verdict.value] += 1

    per_class: dict[str, ClassMetrics] = {}
    for cls in TRUE_CLASSES:
        support = sum(confusion[cls].values())

        if cls == "FP":
            predicted_count = sum(1 for r in scored_records if r.verdict in FP_ACCEPTED_VERDICTS)
            true_positives = sum(confusion["FP"][v.value] for v in FP_ACCEPTED_VERDICTS)
        else:
            target = SINGLE_CLASS_VERDICT[cls]
            predicted_count = sum(1 for r in scored_records if r.verdict is target)
            true_positives = confusion[cls][target.value]

        precision = true_positives / predicted_count if predicted_count else None
        recall = true_positives / support if support else None
        per_class[cls] = ClassMetrics(precision, recall, _f1(precision, recall), support)

    return Report(
        per_class=per_class,
        macro_precision=_macro([m.precision for m in per_class.values()]),
        macro_recall=_macro([m.recall for m in per_class.values()]),
        macro_f1=_macro([m.f1 for m in per_class.values()]),
        confusion=confusion,
        excluded_null=excluded_null,
        no_verdict=no_verdict,
        scored=len(scored_records),
    )


@dataclass
class ComparisonReport:
    """Both paths, scored the same way, for a side-by-side report."""

    agent: Report
    rule: Report
    majority_baseline_share: float = field(default_factory=majority_baseline_share)
    majority_baseline_class: str = field(default_factory=majority_baseline_class)


def compare(
    agent_records: list[VerdictRecord], rule_records: list[VerdictRecord]
) -> ComparisonReport:
    """Score both paths and package them for `format_report`."""
    return ComparisonReport(agent=score(agent_records), rule=score(rule_records))


# --- reporting -------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _class_row(name: str, agent: ClassMetrics, rule: ClassMetrics) -> str:
    return (
        f"{name:<13}"
        f"{_pct(agent.precision):>7}{_pct(agent.recall):>7}{_pct(agent.f1):>7}{agent.support:>5}"
        f"   |"
        f"{_pct(rule.precision):>7}{_pct(rule.recall):>7}{_pct(rule.f1):>7}{rule.support:>5}"
    )


def format_report(report: ComparisonReport) -> str:
    """The side-by-side text report: declared ceiling, majority baseline,
    per-class table, macro average, and the runs that were not scored."""
    lines = [
        "=" * 78,
        "  AGENT vs. RULE BASELINE  (D-013)",
        "=" * 78,
        "",
        "Known ceiling - declared here, not left to be found in the matrix:",
        "  - EXPLAINED is unreachable by the rule path (D-021): the rules never",
        "    compare odd/even depth or search for a secondary eclipse.",
        "  - INSTRUMENTAL/FA is unreachable by BOTH paths (D-035): the TOI queue",
        "    carries no light curve, so neither path is given an instrumental",
        "    check. A predicted INSTRUMENTAL from either side is not grounded.",
        "",
        (
            f"Majority-class baseline (D-015, pinned catalog proportions): "
            f"{_pct(report.majority_baseline_share)}"
        ),
        (
            f"  (always predicting {report.majority_baseline_class} - the class the "
            f"largest disposition maps to)"
        ),
        "Raw accuracy is not reported as a headline metric (D-015).",
        "",
        f"{'':<13}{'agent':^26}   |{'rule':^26}",
        f"{'class':<13}{'P':>7}{'R':>7}{'F1':>7}{'n':>5}   |{'P':>7}{'R':>7}{'F1':>7}{'n':>5}",
        "-" * 78,
    ]

    for cls in TRUE_CLASSES:
        lines.append(_class_row(cls, report.agent.per_class[cls], report.rule.per_class[cls]))

    lines.append("-" * 78)
    lines.append(
        _class_row(
            "macro avg",
            ClassMetrics(
                report.agent.macro_precision,
                report.agent.macro_recall,
                report.agent.macro_f1,
                report.agent.scored,
            ),
            ClassMetrics(
                report.rule.macro_precision,
                report.rule.macro_recall,
                report.rule.macro_f1,
                report.rule.scored,
            ),
        )
    )
    lines.append("")

    for label, side in (("agent", report.agent), ("rule", report.rule)):
        lines.append(
            f"{label}: {side.scored} scored, "
            f"{side.excluded_null} excluded (unlabelled disposition), "
            f"{sum(side.no_verdict.values())} without a verdict"
        )
        if side.no_verdict:
            lines.append("  no verdict, by stop_reason (not a classification error):")
            for reason, count in sorted(side.no_verdict.items()):
                lines.append(f"    {reason}: {count}")

    return "\n".join(lines)
