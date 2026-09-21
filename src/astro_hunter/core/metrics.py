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
The rule engine's only route to `EXPLAINED` is the implied-radius check
(D-039): a stellar radius on the signal and a dilution-corrected depth large
enough to imply an eclipsing body above ~2 R_Jup. It has no odd/even-depth or
secondary-eclipse check (D-021), so an on-target eclipsing binary whose
implied radius does not clear that ceiling - most of them, per D-039's
measurement - is invisible to it by any route. `INSTRUMENTAL` is reachable
by both paths (D-040, D-041) only for a target with a cached TESS 2-minute
light curve - 44 of the 54 pinned-baseline signals, not all of them (D-040).
For the other 10, `check_instrumental_coincidence` returns `assessed: false`
and produces no verdict, on both paths identically - never silently read as
"clean". `scripts/11_rule_triage.py` wires exactly the tools
`scripts/20_agent_triage.py` exposes to the agent, and no more (D-035). If a
check is ever added to one path, it must be added to both, or the comparison
starts measuring evidence access instead of judgement.

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

# The same six dispositions collapse to two groups on the truth side - resolved
# needs no human attention (KP, CP, FA, FP), needs-review does (PC, APC) - the
# identical split `Verdict.is_resolved` already encodes on the verdict side.
NEEDS_REVIEW_DISPOSITIONS: frozenset[str] = frozenset({"PC", "APC"})
RESOLVED_DISPOSITIONS: frozenset[str] = frozenset({"KP", "CP", "FA", "FP"})

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
    confidence: float | None = None


def record_from_dict(d: dict) -> VerdictRecord:
    """Adapt one run-file entry (agent or rule shape; they share field names)."""
    raw_verdict = d.get("verdict")
    return VerdictRecord(
        signal_id=d["signal_id"],
        true_disposition=d.get("true_disposition"),
        verdict=Verdict(raw_verdict) if raw_verdict else None,
        stop_reason=d.get("stop_reason"),
        confidence=d.get("confidence"),
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


def _split_scorable(
    records: list[VerdictRecord],
) -> tuple[list[VerdictRecord], int, Counter]:
    """Three-way split shared by every scoring function.

    A null/unlabelled disposition is not a class (D-015) and a missing
    verdict is not a classification error (D-031-adjacent reasoning, applied
    here) - both are counted, neither is scored.
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

    return scored_records, excluded_null, no_verdict


def score(records: list[VerdictRecord]) -> Report:
    """Confusion matrix and per-class precision/recall/F1 for one path."""
    scored_records, excluded_null, no_verdict = _split_scorable(records)

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


@dataclass(frozen=True)
class BinaryReport:
    """Resolved-vs-needs-review, alongside the per-class `Report`, not instead
    of it (D-0xx). Two numbers only, because only two matter here.

    `queue_reduction` is an efficiency number: the fraction of the queue a
    resolved verdict removes from human attention. It says nothing about
    whether that removal was correct.

    `needs_review_discarded` is the safety constraint: a true `PC`/`APC`
    signal (`NEEDS_REVIEW_DISPOSITIONS`) whose verdict came back resolved
    (`Verdict.is_resolved`) anyway, and would therefore leave the queue with
    no human ever looking at it. A high `queue_reduction` next to a non-zero
    `needs_review_discarded` is not a result to be satisfied with: efficient
    is not the same as safe, and this is the number that says which one a
    result actually is.
    """

    queue_reduction: float | None  # resolved verdicts / scored, whole path
    needs_review_total: int  # true PC/APC signals scored
    needs_review_discarded: int  # of those, verdict.is_resolved anyway
    discarded_signal_ids: tuple[str, ...]
    scored: int
    excluded_null: int
    no_verdict: Counter


def score_binary(records: list[VerdictRecord]) -> BinaryReport:
    """Collapse the six dispositions/verdicts to resolved-vs-needs-review.

    Same exclusion rules as `score` (`_split_scorable`): a null disposition is
    not a class, a missing verdict is not a classification error. Applied
    once, shared by both views of the same records.
    """
    scored_records, excluded_null, no_verdict = _split_scorable(records)

    resolved_count = sum(1 for r in scored_records if r.verdict.is_resolved)
    queue_reduction = resolved_count / len(scored_records) if scored_records else None

    needs_review = [r for r in scored_records if r.true_disposition in NEEDS_REVIEW_DISPOSITIONS]
    discarded = [r for r in needs_review if r.verdict.is_resolved]

    return BinaryReport(
        queue_reduction=queue_reduction,
        needs_review_total=len(needs_review),
        needs_review_discarded=len(discarded),
        discarded_signal_ids=tuple(r.signal_id for r in discarded),
        scored=len(scored_records),
        excluded_null=excluded_null,
        no_verdict=no_verdict,
    )


@dataclass(frozen=True)
class OrderedQueue:
    """Scored records ranked the way a reviewer would actually work through
    them - alongside `score_binary`, not instead of it (D-0xx): that reports
    how many needs-review signals get discarded; this asks, of what is left
    in the queue, what order they should be looked at in.

    Resolved verdicts (`Verdict.is_resolved`) sink to the bottom - nothing
    left for a human to decide there, whether or not that resolution was
    correct (`score_binary` is what catches a wrong one). Everything still
    needing review (`INTERESTING`, `INSUFFICIENT`) surfaces first, ranked by
    `confidence` descending: the signal the path is most confident is worth
    attention comes first.

    A record with no `confidence` value ranks last *within its own bucket*
    (still ahead of every resolved verdict, if it needs review) - "when
    available" (as specified) means a missing confidence is not read as
    zero, nor as worth skipping the queue for; it is simply not a basis to
    claim priority over a record that does carry one.
    """

    records: tuple[VerdictRecord, ...]
    excluded_null: int
    no_verdict: Counter


def _queue_sort_key(r: VerdictRecord) -> tuple[bool, float]:
    needs_review_last = r.verdict.is_resolved  # False (needs review) sorts first
    confidence_rank = -r.confidence if r.confidence is not None else float("inf")
    return (needs_review_last, confidence_rank)


def order_queue(records: list[VerdictRecord]) -> OrderedQueue:
    """Rank scored records for review order. Same exclusions as `score`
    (`_split_scorable`): a null disposition and a missing verdict are both
    counted, neither is scored or ranked - `Verdict.is_resolved` is not
    defined without a verdict to ask it of.
    """
    scored_records, excluded_null, no_verdict = _split_scorable(records)
    ordered = sorted(scored_records, key=_queue_sort_key)
    return OrderedQueue(
        records=tuple(ordered), excluded_null=excluded_null, no_verdict=no_verdict
    )


@dataclass(frozen=True)
class PrecisionAtK:
    """Of the top `k` signals in an `OrderedQueue`, how many are a true
    `PC`/`APC` - the fraction of a reviewer's attention, spent strictly
    top-down, that would land on a signal actually worth it.

    `n` is the number of records actually ranked, `min(k, len(queue))` - when
    the queue is shorter than `k`, `precision` is computed over `n` records,
    not silently reported as if `k` had been reached (same reasoning as
    `_macro`: an undefined or partial ratio is not the same claim as a bad
    one). `precision` is `None` only when `n` is 0.
    """

    k: int
    n: int
    true_positives: int
    precision: float | None


# Reviewer-relevant checkpoints: a short first pass, a typical daily batch,
# a generous one. Not fitted to any one run's queue length.
PRECISION_AT_K_VALUES: tuple[int, ...] = (5, 10, 20)


def precision_at_k(queue: OrderedQueue, k: int) -> PrecisionAtK:
    top = queue.records[:k]
    n = len(top)
    true_positives = sum(1 for r in top if r.true_disposition in NEEDS_REVIEW_DISPOSITIONS)
    return PrecisionAtK(
        k=k, n=n, true_positives=true_positives, precision=(true_positives / n if n else None)
    )


@dataclass
class ComparisonReport:
    """Both paths, scored the same way, for a side-by-side report."""

    agent: Report
    rule: Report
    agent_binary: BinaryReport
    rule_binary: BinaryReport
    majority_baseline_share: float = field(default_factory=majority_baseline_share)
    majority_baseline_class: str = field(default_factory=majority_baseline_class)


def compare(
    agent_records: list[VerdictRecord], rule_records: list[VerdictRecord]
) -> ComparisonReport:
    """Score both paths and package them for `format_report`."""
    return ComparisonReport(
        agent=score(agent_records),
        rule=score(rule_records),
        agent_binary=score_binary(agent_records),
        rule_binary=score_binary(rule_records),
    )


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
        "  - EXPLAINED is reachable by the rule path only via implied radius",
        "    (D-039, needs a stellar radius); it has no odd/even-depth or",
        "    secondary-eclipse check, so most on-target eclipsing binaries",
        "    still escape it.",
        "  - INSTRUMENTAL/FA is reachable by BOTH paths only for a target with",
        "    a cached TESS 2-minute light curve (D-040/D-041) - 44 of 54 in the",
        "    pinned baseline. For the other 10, the check is not assessed and",
        "    produces no verdict on either side; it is never read as clean.",
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

    lines.append("Binary (resolved vs. needs-review, alongside the per-class table above):")
    lines.append("  KP/CP/FA/FP -> resolved, no human attention needed; PC/APC -> needs-review.")
    for label, binary in (("agent", report.agent_binary), ("rule", report.rule_binary)):
        lines.append(f"  {label}: queue reduction {_pct(binary.queue_reduction)}")
        lines.append(
            f"    needs-review signals discarded as resolved: "
            f"{binary.needs_review_discarded}/{binary.needs_review_total}"
            + (
                f" ({', '.join(binary.discarded_signal_ids)})"
                if binary.discarded_signal_ids
                else ""
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
