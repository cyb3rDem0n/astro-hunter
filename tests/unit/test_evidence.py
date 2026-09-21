"""Evidence collection and the deterministic verdict baseline."""

from datetime import UTC, datetime

import pytest

from astro_hunter.core.evidence import build_dossier, collect_evidence, derive_verdict
from astro_hunter.core.models import Evidence, EvidenceKind, Signal, Verdict

POS = {"ra_deg": 84.29928, "dec_deg": -80.464604}


def sig(**kw):
    return Signal(signal_id="X.01", source="test", **POS, **kw)


def ev(kind, source="test", summary="s", **payload):
    return Evidence(kind=kind, source=source, summary=summary,
                    retrieved_at=datetime.now(UTC),
                    identifier=payload.pop("identifier", None),
                    separation_arcsec=payload.pop("separation_arcsec", None),
                    payload=payload)


def dossier_with(*evidence):
    return collect_evidence(sig(), {"fake": lambda s: list(evidence)})


# --- collection ---------------------------------------------------------------

def test_every_check_runs_even_after_a_conclusive_one():
    """Stopping early would save queries and impoverish the dossier."""
    calls = []

    def make(name):
        def check(s):
            calls.append(name)
            return [ev(EvidenceKind.CATALOG_MATCH, identifier="X b",
                       period_relation="match")]
        return check

    d = collect_evidence(sig(), {"a": make("a"), "b": make("b"), "c": make("c")})
    assert calls == ["a", "b", "c"]
    assert len(d.evidence) == 3


def test_a_failing_check_is_recorded_not_swallowed():
    def broken(s):
        raise RuntimeError("archive unreachable")

    d = collect_evidence(sig(), {"catalogs": broken})
    assert len(d.evidence) == 1
    assert d.evidence[0].payload["failed"] is True
    assert "unreachable" in d.evidence[0].summary
    assert d.evidence[0].source


def test_a_failing_check_does_not_stop_the_others():
    def broken(s):
        raise RuntimeError("down")

    def fine(s):
        return [ev(EvidenceKind.NEIGHBOUR)]

    d = collect_evidence(sig(), {"broken": broken, "fine": fine})
    assert len(d.evidence) == 2
    assert d.tools_called == ["broken", "fine"]


def test_timings_are_recorded():
    d = collect_evidence(sig(), {"noop": lambda s: []})
    assert d.started_at and d.finished_at
    assert d.finished_at >= d.started_at


# --- verdict rules ------------------------------------------------------------

def test_matching_period_on_a_catalogued_planet_is_known():
    d = dossier_with(ev(EvidenceKind.CATALOG_MATCH, identifier="pi Men c",
                        period_relation="match"))
    verdict, confidence, why = derive_verdict(d)
    assert verdict is Verdict.KNOWN
    assert confidence > 0.9
    assert "pi Men c" in why


def test_a_harmonic_is_still_the_same_planet():
    """The classic blind-search failure: locking onto twice the true period."""
    d = dossier_with(ev(EvidenceKind.CATALOG_MATCH, identifier="pi Men c",
                        period_relation="harmonic:2"))
    verdict, _, why = derive_verdict(d)
    assert verdict is Verdict.KNOWN
    assert "2" in why


def test_flagged_cadences_win_over_contamination():
    """Rule order: an instrumental explanation is cheaper and more decisive."""
    d = dossier_with(
        ev(EvidenceKind.DERIVED, source="dilution correction",
           corrected_depth_ppm=200_000),
        ev(EvidenceKind.INSTRUMENTAL_WINDOW, flagged_fraction=0.6),
    )
    assert derive_verdict(d)[0] is Verdict.INSTRUMENTAL


def test_most_transits_in_gaps_is_instrumental():
    d = dossier_with(ev(EvidenceKind.INSTRUMENTAL_WINDOW,
                        transits_in_gaps=4, predicted_transits=5))
    verdict, _, why = derive_verdict(d)
    assert verdict is Verdict.INSTRUMENTAL
    assert "alias" in why


def test_a_few_transits_in_gaps_is_not_enough_to_condemn():
    """Partial coverage is normal; only a majority suggests an alias."""
    d = dossier_with(ev(EvidenceKind.INSTRUMENTAL_WINDOW,
                        transits_in_gaps=1, predicted_transits=5))
    assert derive_verdict(d)[0] is not Verdict.INSTRUMENTAL


def test_too_few_covered_transits_is_insufficient():
    d = dossier_with(ev(EvidenceKind.INSTRUMENTAL_WINDOW,
                        observed_transits=1, minimum_required=2))
    assert derive_verdict(d)[0] is Verdict.INSUFFICIENT


def test_a_neighbour_that_merely_cannot_be_excluded_is_not_contamination():
    """The D-030 regression, now enforced in the rule engine too: almost every
    neighbour clears `could_explain_signal`, so that alone must not condemn."""
    d = dossier_with(
        ev(EvidenceKind.NEIGHBOUR, identifier="n1", separation_arcsec=4.2,
           could_explain_signal=True, max_producible_depth_ppm=8000,
           flux_ratio=0.05),
        ev(EvidenceKind.NEIGHBOUR, source="test", dilution=0.9),
    )
    assert derive_verdict(d)[0] is Verdict.INTERESTING


def test_a_small_target_share_beside_a_much_brighter_star_is_contamination():
    d = dossier_with(
        ev(EvidenceKind.NEIGHBOUR, source="test", dilution=0.1),
        ev(EvidenceKind.NEIGHBOUR, identifier="n1", separation_arcsec=4.2,
           flux_ratio=15.0, could_explain_signal=True,
           max_producible_depth_ppm=8000),
    )
    verdict, _, why = derive_verdict(d)
    assert verdict is Verdict.CONTAMINATED
    assert "n1" in why


def test_a_small_target_share_alone_is_not_enough_without_a_bright_culprit():
    """Many faint neighbours can dilute the aperture without any one of them
    being a plausible culprit - the fraction alone is not the criterion."""
    d = dossier_with(
        ev(EvidenceKind.NEIGHBOUR, source="test", dilution=0.1),
        ev(EvidenceKind.NEIGHBOUR, identifier="n1", separation_arcsec=4.2,
           flux_ratio=2.0, could_explain_signal=True,
           max_producible_depth_ppm=8000),
    )
    assert derive_verdict(d)[0] is Verdict.INTERESTING


def test_the_brightest_culprit_is_the_one_named():
    d = dossier_with(
        ev(EvidenceKind.NEIGHBOUR, source="test", dilution=0.05),
        ev(EvidenceKind.NEIGHBOUR, identifier="weak", separation_arcsec=2.0,
           flux_ratio=11.0, could_explain_signal=True,
           max_producible_depth_ppm=400),
        ev(EvidenceKind.NEIGHBOUR, identifier="strong", separation_arcsec=9.0,
           flux_ratio=18.0, could_explain_signal=True,
           max_producible_depth_ppm=9000),
    )
    assert "strong" in derive_verdict(d)[2]


def test_an_implied_radius_above_the_ceiling_is_explained_not_contaminated():
    """D-039: a real stellar radius makes this a grounded planet/star radius
    test, and the answer it gives - a stellar companion on the target - is
    EXPLAINED, not CONTAMINATED (which means a neighbour, not the target)."""
    d = dossier_with(
        ev(EvidenceKind.DERIVED, source="implied radius",
           st_rad_rsun=1.0, implied_radius_rjup=4.5),
    )
    verdict, confidence, why = derive_verdict(d)
    assert verdict is Verdict.EXPLAINED
    assert confidence == pytest.approx(0.7)
    assert "4.5" in why and "stellar companion" in why


def test_an_implied_radius_below_the_ceiling_is_not_explained():
    d = dossier_with(
        ev(EvidenceKind.DERIVED, source="implied radius",
           st_rad_rsun=1.0, implied_radius_rjup=1.1),
    )
    assert derive_verdict(d)[0] is not Verdict.EXPLAINED


def test_implied_radius_takes_priority_over_the_ppm_proxy_when_both_are_present():
    """5b supersedes 5c (D-039): once a real stellar radius is available, the
    coarse ppm-only proxy must not override what the actual physics says."""
    d = dossier_with(
        ev(EvidenceKind.DERIVED, source="dilution correction",
           corrected_depth_ppm=200_000, dilution=0.5),
        ev(EvidenceKind.DERIVED, source="implied radius",
           st_rad_rsun=0.2, implied_radius_rjup=0.8),
    )
    verdict, _, _ = derive_verdict(d)
    assert verdict is not Verdict.CONTAMINATED


def test_missing_stellar_radius_falls_back_to_the_ppm_proxy_unaffected():
    """No st_rad on the signal means no implied-radius evidence at all (per
    neighbours.crossmatch_neighbours): rule 5c must still fire exactly as it
    did before D-039 - absence of the input produces no verdict of its own,
    it just leaves the older rule in charge."""
    d = dossier_with(
        ev(EvidenceKind.DERIVED, source="dilution correction",
           observed_depth_ppm=3000, corrected_depth_ppm=485_000, dilution=0.006),
    )
    verdict, _, why = derive_verdict(d)
    assert verdict is Verdict.CONTAMINATED
    assert "implausible" in why


def test_a_physically_implausible_corrected_depth_is_contamination():
    d = dossier_with(
        ev(EvidenceKind.DERIVED, source="dilution correction",
           observed_depth_ppm=3000, corrected_depth_ppm=485_000, dilution=0.006),
    )
    verdict, _, why = derive_verdict(d)
    assert verdict is Verdict.CONTAMINATED
    assert "implausible" in why


def test_a_modest_corrected_depth_is_not_contamination():
    d = dossier_with(
        ev(EvidenceKind.DERIVED, source="dilution correction",
           observed_depth_ppm=300, corrected_depth_ppm=1200, dilution=0.25),
    )
    assert derive_verdict(d)[0] is Verdict.INTERESTING


def test_a_significant_odd_even_difference_is_explained():
    """D-038's gap, closed: direct photometric evidence of an eclipsing
    binary at twice the search period."""
    d = dossier_with(
        ev(EvidenceKind.DERIVED, source="light curve (odd/even depth)",
           odd_depth_ppm=20_000.0, even_depth_ppm=10_000.0,
           odd_transits=5, even_transits=5,
           odd_even_sigma=8.4, odd_even_significant=True),
    )
    verdict, confidence, why = derive_verdict(d)
    assert verdict is Verdict.EXPLAINED
    assert confidence == pytest.approx(0.7)
    assert "eclipsing binary" in why
    assert "20000" in why.replace(",", "") and "10000" in why.replace(",", "")


def test_a_non_significant_odd_even_difference_does_not_drive_a_verdict():
    d = dossier_with(
        ev(EvidenceKind.DERIVED, source="light curve (odd/even depth)",
           odd_depth_ppm=10_100.0, even_depth_ppm=10_000.0,
           odd_transits=5, even_transits=5,
           odd_even_sigma=0.4, odd_even_significant=False),
    )
    verdict, _, _ = derive_verdict(d)
    assert verdict is not Verdict.EXPLAINED


def test_an_unassessed_odd_even_check_does_not_drive_a_verdict():
    """Too few transits per group produces `assessed: False` with no
    `odd_even_significant` key - absence of that key must not be read as
    either outcome."""
    d = dossier_with(
        ev(EvidenceKind.DERIVED, source="light curve (odd/even depth)",
           odd_transits=1, even_transits=1, minimum_required_per_group=3),
    )
    verdict, _, _ = derive_verdict(d)
    assert verdict is not Verdict.EXPLAINED


def test_known_host_with_an_unrelated_period_is_interesting():
    """The case worth protecting: additional planets live in known systems."""
    d = dossier_with(ev(EvidenceKind.CATALOG_MATCH, identifier="pi Men c",
                        period_relation="unrelated"))
    verdict, _, why = derive_verdict(d)
    assert verdict is Verdict.INTERESTING
    assert "additional planet" in why


def test_nothing_found_anywhere_is_interesting():
    d = dossier_with(ev(EvidenceKind.CATALOG_MATCH, matches=0))
    assert derive_verdict(d)[0] is Verdict.INTERESTING


def test_a_failed_check_makes_the_result_insufficient_not_interesting():
    """Silence from a broken archive must not read as a clean result."""
    def broken(s):
        raise RuntimeError("timeout")

    d = collect_evidence(sig(), {"catalogs": broken})
    verdict, _, why = derive_verdict(d)
    assert verdict is Verdict.INSUFFICIENT
    assert "catalogs" in why


def test_a_real_match_still_wins_over_a_failed_check():
    def broken(s):
        raise RuntimeError("timeout")

    def matched(s):
        return [ev(EvidenceKind.CATALOG_MATCH, identifier="X b",
                   period_relation="match")]

    d = collect_evidence(sig(), {"neighbours": broken, "catalogs": matched})
    assert derive_verdict(d)[0] is Verdict.KNOWN


# --- end to end ---------------------------------------------------------------

def test_build_dossier_attaches_the_verdict():
    d = build_dossier(sig(), {"c": lambda s: [
        ev(EvidenceKind.CATALOG_MATCH, identifier="pi Men c", period_relation="match")
    ]})
    assert d.verdict is Verdict.KNOWN
    assert d.confidence == pytest.approx(0.95)
    assert d.reasoning
    assert d.sources_consulted


def test_every_verdict_comes_with_a_reason():
    """A verdict without a stated reason is an assertion, which D-014 forbids."""
    cases = [
        [ev(EvidenceKind.CATALOG_MATCH, identifier="a", period_relation="match")],
        [ev(EvidenceKind.INSTRUMENTAL_WINDOW, flagged_fraction=0.9)],
        [ev(EvidenceKind.NEIGHBOUR, identifier="n", separation_arcsec=1.0,
            could_explain_signal=True, max_producible_depth_ppm=999)],
        [ev(EvidenceKind.CATALOG_MATCH, matches=0)],
    ]
    for evidence in cases:
        d = build_dossier(sig(), {"c": lambda s, e=evidence: e})
        assert d.reasoning and d.confidence is not None


def test_no_target_at_the_position_is_insufficient_not_contaminated():
    """Regression: an empty position used to be judged CONTAMINATED, because a
    distant source was promoted to target and then out-shone by another."""
    d = dossier_with(ev(EvidenceKind.NEIGHBOUR, target_found=False))
    verdict, _, why = derive_verdict(d)
    assert verdict is Verdict.INSUFFICIENT
    assert "close enough" in why


def test_a_doubtful_target_identification_blocks_a_confident_verdict():
    d = dossier_with(
        ev(EvidenceKind.NEIGHBOUR, target_identification_doubtful=True,
           brighter_neighbours=1),
        ev(EvidenceKind.NEIGHBOUR, identifier="n", separation_arcsec=5.0,
           could_explain_signal=True, max_producible_depth_ppm=9000),
    )
    assert derive_verdict(d)[0] is Verdict.INSUFFICIENT
