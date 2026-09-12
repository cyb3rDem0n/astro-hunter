"""Evaluation against expert dispositions (D-013). No network, no model calls."""

import pytest

from astro_hunter.core.metrics import (
    ClassMetrics,
    VerdictRecord,
    compare,
    format_report,
    majority_baseline_class,
    majority_baseline_share,
    record_from_dict,
    score,
)
from astro_hunter.core.models import Verdict


def rec(signal_id, true_disposition, verdict, stop_reason=None):
    return VerdictRecord(
        signal_id=signal_id,
        true_disposition=true_disposition,
        verdict=verdict,
        stop_reason=stop_reason,
    )


# --- D-017: FP accepts two verdicts --------------------------------------------


def test_fp_accepts_either_verdict():
    """Both a demonstrated neighbour and an on-target binary are a correct
    read of a TESS false positive (D-017); recall must not penalise either."""
    records = [
        rec("a", "FP", Verdict.CONTAMINATED),
        rec("b", "FP", Verdict.EXPLAINED),
    ]
    report = score(records)
    assert report.per_class["FP"].recall == pytest.approx(1.0)
    assert report.per_class["FP"].precision == pytest.approx(1.0)


def test_the_matrix_still_records_which_verdict_was_produced():
    """D-017: scoring both as correct must not erase which one happened."""
    records = [
        rec("a", "FP", Verdict.CONTAMINATED),
        rec("b", "FP", Verdict.EXPLAINED),
    ]
    report = score(records)
    assert report.confusion["FP"]["contaminated"] == 1
    assert report.confusion["FP"]["explained"] == 1


def test_an_unrelated_verdict_on_an_fp_row_is_not_accepted():
    records = [rec("a", "FP", Verdict.INTERESTING)]
    report = score(records)
    assert report.per_class["FP"].recall == pytest.approx(0.0)
    assert report.confusion["FP"]["interesting"] == 1


def test_a_false_fp_prediction_costs_precision_not_recall_elsewhere():
    """A KNOWN-true signal misread as CONTAMINATED inflates the FP-class
    prediction count without being a true positive for it - that is what
    precision, not recall, is supposed to catch."""
    records = [
        rec("a", "FP", Verdict.CONTAMINATED),  # correct
        rec("b", "KP", Verdict.CONTAMINATED),  # wrong: true class is KNOWN
    ]
    report = score(records)
    assert report.per_class["FP"].precision == pytest.approx(0.5)
    assert report.per_class["KNOWN"].recall == pytest.approx(0.0)


# --- no verdict is not a classification error ----------------------------------


def test_no_verdict_runs_are_counted_not_scored():
    records = [
        rec("a", "PC", None, stop_reason="max_iterations"),
        rec("b", "PC", Verdict.INTERESTING),
    ]
    report = score(records)
    assert report.scored == 1
    assert report.no_verdict == {"max_iterations": 1}
    # the missing-verdict signal must not appear as a wrong prediction
    assert report.per_class["INTERESTING"].support == 1
    assert report.per_class["INTERESTING"].recall == pytest.approx(1.0)


def test_no_verdict_reasons_are_tallied_separately():
    records = [
        rec("a", "PC", None, stop_reason="api_error"),
        rec("b", "APC", None, stop_reason="api_error"),
        rec("c", "PC", None, stop_reason="max_iterations"),
    ]
    report = score(records)
    assert report.no_verdict == {"api_error": 2, "max_iterations": 1}
    assert report.scored == 0


# --- null disposition is excluded, not a class ---------------------------------


def test_unlabelled_disposition_is_excluded_from_scoring():
    records = [
        rec("a", None, Verdict.INTERESTING),
        rec("b", "", Verdict.KNOWN),
        rec("c", "PC", Verdict.INTERESTING),
    ]
    report = score(records)
    assert report.excluded_null == 2
    assert report.scored == 1


# --- majority baseline (D-015) --------------------------------------------------


def test_majority_baseline_is_the_pinned_pc_share():
    """4836 of 8134 labelled rows (excluding the 14 null rows) are PC (D-015) -
    real catalog proportions, not the stratified sample's."""
    assert majority_baseline_share() == pytest.approx(4836 / 8134, abs=1e-6)
    assert majority_baseline_share() == pytest.approx(0.595, abs=0.001)


def test_majority_baseline_class_is_pcs_mapped_verdict():
    assert majority_baseline_class() == "INTERESTING"


# --- macro average ---------------------------------------------------------------


def test_macro_average_is_the_mean_of_defined_per_class_values():
    """One correct signal per class scores every class 1.0, so the macro
    average must also be 1.0 - a basic sanity check on the aggregation."""
    records = [
        rec("a", "KP", Verdict.KNOWN),
        rec("b", "FA", Verdict.INSTRUMENTAL),
        rec("c", "FP", Verdict.CONTAMINATED),
        rec("d", "PC", Verdict.INTERESTING),
        rec("e", "APC", Verdict.INSUFFICIENT),
    ]
    report = score(records)
    assert report.macro_precision == pytest.approx(1.0)
    assert report.macro_recall == pytest.approx(1.0)
    assert report.macro_f1 == pytest.approx(1.0)


def test_a_class_with_no_support_is_excluded_from_the_macro_average():
    """A class absent from this run has undefined recall (0/0), not zero
    recall - averaging it in as 0 would understate a result that simply
    never saw that class, so it is left out instead (documented in
    core.metrics._macro)."""
    records = [
        rec("a", "KP", Verdict.KNOWN),
        rec("b", "PC", Verdict.INTERESTING),
    ]
    report = score(records)
    assert report.per_class["INSTRUMENTAL"].recall is None
    assert report.per_class["FP"].recall is None
    # only KNOWN and INTERESTING have support; both are perfect
    assert report.macro_recall == pytest.approx(1.0)


# --- adapters --------------------------------------------------------------------


def test_record_from_dict_reads_the_shared_run_file_shape():
    d = {
        "signal_id": "TOI-1.01",
        "verdict": "known",
        "true_disposition": "CP",
        "stop_reason": "completed",
    }
    r = record_from_dict(d)
    assert r.verdict is Verdict.KNOWN
    assert r.true_disposition == "CP"


def test_record_from_dict_handles_a_null_verdict():
    d = {
        "signal_id": "TOI-1.01",
        "verdict": None,
        "true_disposition": "PC",
        "stop_reason": "max_iterations",
    }
    r = record_from_dict(d)
    assert r.verdict is None
    assert r.stop_reason == "max_iterations"


# --- report formatting ------------------------------------------------------------


def test_the_declared_ceiling_is_stated_explicitly_in_the_report():
    """D-021/D-035: this must be readable as a stated fact, not something the
    reader has to infer from an empty matrix cell."""
    report = compare([], [])
    text = format_report(report)
    assert "EXPLAINED is unreachable by the rule path" in text
    assert "INSTRUMENTAL/FA is unreachable by BOTH paths" in text


def test_the_report_states_the_majority_baseline_and_disclaims_raw_accuracy():
    report = compare([], [])
    text = format_report(report)
    assert "59.5%" in text
    assert "Raw accuracy is not reported as a headline metric" in text


def test_the_report_lists_no_verdict_reasons_per_path():
    agent = [rec("a", "PC", None, stop_reason="max_iterations")]
    report = compare(agent, [])
    text = format_report(report)
    assert "max_iterations: 1" in text


def test_undefined_metrics_print_as_na_not_a_crash():
    report = compare([], [])
    text = format_report(report)
    assert "n/a" in text


def test_class_metrics_is_a_plain_value_object():
    m = ClassMetrics(precision=0.5, recall=1.0, f1=pytest.approx(2 / 3), support=2)
    assert m.support == 2
