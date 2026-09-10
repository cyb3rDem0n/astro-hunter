"""Instrumental coincidence checks.

Everything here is synthetic and offline: the observing record is constructed
so the expected answer is known by construction, which is the same principle as
the injection tests in the photometry package (D-010).
"""

import numpy as np
import pytest
from lightkurve.utils import TessQualityFlags as Q

from astro_hunter.core.models import Signal
from astro_hunter.domains.exoplanets.instrumental import (
    assess_transit,
    check_instrumental,
    median_cadence,
    predicted_transit_times,
)

CADENCE = 120 / 86400          # 2 minutes, in days
SECTOR = 27.4                  # days
POS = {"ra_deg": 84.29928, "dec_deg": -80.464604}


def observing_record(days=SECTOR, gaps=()):
    """A TESS-like time array with optional (start, end) gaps punched out."""
    t = np.arange(0.0, days, CADENCE)
    for start, end in gaps:
        t = t[(t < start) | (t > end)]
    return t


def signal(period=6.27, epoch=1.5, duration_h=2.8):
    return Signal(signal_id="X.01", source="test", period_days=period,
                  epoch=epoch, duration_hours=duration_h, **POS)


# --- cadence ------------------------------------------------------------------

def test_cadence_is_robust_to_gaps():
    """A mean would be dragged up by the downlink gap; the median is not."""
    t = observing_record(gaps=[(13.0, 14.5)])
    assert median_cadence(t) == pytest.approx(CADENCE, rel=1e-6)


def test_cadence_needs_two_samples():
    with pytest.raises(ValueError, match="two samples"):
        median_cadence(np.array([1.0]))


# --- ephemeris ----------------------------------------------------------------

def test_predicted_transits_span_the_baseline():
    times = predicted_transit_times(epoch=1.5, period_days=6.27,
                                    t_start=0.0, t_end=SECTOR)
    assert times[0] == pytest.approx(1.5)
    assert all(0.0 <= t <= SECTOR for t in times)
    assert np.allclose(np.diff(times), 6.27)


def test_epoch_before_the_baseline_is_projected_forward():
    """An ephemeris from an earlier sector must still place events here."""
    times = predicted_transit_times(epoch=-100.0, period_days=6.27,
                                    t_start=0.0, t_end=SECTOR)
    assert len(times) >= 4


def test_non_positive_period_is_rejected():
    with pytest.raises(ValueError, match="positive"):
        predicted_transit_times(1.0, 0.0, 0.0, 10.0)


# --- single transit -----------------------------------------------------------

def test_a_fully_covered_transit_is_observed():
    t = observing_record()
    result = assess_transit(t, None, mid=5.0, duration_days=2.8 / 24, cadence=CADENCE)
    assert result["coverage"] == pytest.approx(1.0, abs=0.05)
    assert result["observed"]


def test_a_transit_inside_a_gap_is_not_observed():
    t = observing_record(gaps=[(4.9, 5.1)])
    result = assess_transit(t, None, mid=5.0, duration_days=2.8 / 24, cadence=CADENCE)
    assert result["cadences_present"] == 0
    assert not result["observed"]


def test_flagged_cadences_are_counted():
    t = observing_record()
    quality = np.zeros(len(t), dtype=int)
    quality[(t > 4.9) & (t < 5.1)] = Q.Desat        # a momentum dump on the transit
    result = assess_transit(t, quality, mid=5.0, duration_days=2.8 / 24, cadence=CADENCE)
    assert result["flagged_fraction"] == pytest.approx(1.0)


def test_cosmic_rays_are_not_treated_as_spacecraft_events():
    """Single-cadence outliers are removed by cleaning; flagging them here
    would mark healthy data as instrumental."""
    t = observing_record()
    quality = np.zeros(len(t), dtype=int)
    quality[(t > 4.9) & (t < 5.1)] = Q.ApertureCosmic
    result = assess_transit(t, quality, mid=5.0, duration_days=2.8 / 24, cadence=CADENCE)
    assert result["cadences_flagged"] == 0


# --- end to end ---------------------------------------------------------------

def test_a_clean_signal_raises_no_alerts():
    t = observing_record()
    ev = check_instrumental(signal(), t, np.zeros(len(t), dtype=int))
    assert len(ev) == 1
    assert ev[0].payload["observed_transits"] == ev[0].payload["predicted_transits"]


def test_a_period_that_hides_its_transits_in_gaps_is_flagged():
    """The alias case: every predicted event lands where there is no data."""
    period, epoch, half = 5.0, 2.0, 0.1
    gaps = [(epoch + n * period - half, epoch + n * period + half) for n in range(6)]
    t = observing_record(gaps=gaps)

    ev = check_instrumental(signal(period=period, epoch=epoch), t)
    summaries = " ".join(e.summary for e in ev)
    assert "data gaps" in summaries
    assert "alias" in summaries


def test_too_few_covered_transits_is_reported_separately():
    """Coverage and count are different failures and get different evidence.

    Five days at a period of 6.27 admits exactly one event. One event fixes an
    epoch, never a period: any period whose next transit falls outside the
    baseline fits the data equally well.
    """
    t = observing_record(days=5.0)
    ev = check_instrumental(signal(period=6.27, epoch=1.5), t)
    assert ev[0].payload["observed_transits"] == 1
    assert any("not established by the observations" in e.summary for e in ev)


def test_transits_sitting_on_spacecraft_events_are_flagged():
    t = observing_record()
    quality = np.zeros(len(t), dtype=int)
    for n in range(6):
        mid = 1.5 + n * 6.27
        quality[(t > mid - 0.1) & (t < mid + 0.1)] = Q.Straylight
    ev = check_instrumental(signal(), t, quality)
    assert any("spacecraft-event flag" in e.summary for e in ev)


def test_missing_quality_is_declared_not_assumed_clean():
    t = observing_record()
    ev = check_instrumental(signal(), t, quality=None)
    assert ev[0].payload["quality_flags_available"] is False


def test_a_signal_without_an_ephemeris_is_not_assessed():
    t = observing_record()
    bare = Signal(signal_id="X.01", source="test", **POS)
    ev = check_instrumental(bare, t)
    assert ev[0].payload["assessed"] is False


def test_all_evidence_carries_a_source():
    t = observing_record(gaps=[(13.0, 14.5)])
    for e in check_instrumental(signal(), t, np.zeros(len(t), dtype=int)):
        assert e.source.strip()
