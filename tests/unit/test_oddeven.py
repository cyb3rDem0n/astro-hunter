"""Odd/even transit-depth comparison (D-038's gap, closed). No network, no
light-curve I/O - synthetic time/flux arrays exercise the fold and the
statistics directly, the same split `test_tess.py` uses for the
acquisition-side wiring.
"""

import numpy as np
import pytest

from astro_hunter.core.models import Signal
from astro_hunter.domains.exoplanets.oddeven import (
    MIN_TRANSITS_PER_GROUP,
    check_odd_even_depth,
)

PERIOD = 2.0
EPOCH = 1.0
DURATION_DAYS = 0.1
CADENCE = 1.0 / 1440  # 1 minute


def sig(**kw):
    return Signal(signal_id="X.01", source="test", ra_deg=0.0, dec_deg=0.0, **kw)


def folded_light_curve(n_cycles, odd_depth, even_depth, noise=0.0, seed=0):
    """Baseline 1.0, a dip of `odd_depth`/`even_depth` (as a flux fraction)
    at every predicted transit, alternating by cycle parity - cycle 0 is
    even, cycle 1 is odd, matching `oddeven.check_odd_even_depth`'s own
    `cycle % 2` split."""
    # Just enough margin around the simulated cycles for their own local
    # baseline windows - less than one full period on either side, so the
    # observed range never picks up an adjacent, un-simulated predicted
    # transit and silently mixes a phantom zero-depth sample into a group.
    t_start = EPOCH - 0.5
    t_end = EPOCH + (n_cycles - 1) * PERIOD + 0.5
    time = np.arange(t_start, t_end, CADENCE)
    rng = np.random.default_rng(seed)
    flux = np.ones_like(time) + (rng.normal(0, noise, size=time.shape) if noise else 0.0)
    for n in range(n_cycles):
        mid = EPOCH + n * PERIOD
        depth = odd_depth if n % 2 else even_depth
        half = DURATION_DAYS / 2
        flux[(time >= mid - half) & (time <= mid + half)] -= depth
    return time, flux


# --- significance --------------------------------------------------------------


def test_a_real_depth_difference_is_significant():
    """An eclipsing binary at twice the search period: alternating deep and
    shallow eclipses, well above noise."""
    time, flux = folded_light_curve(n_cycles=8, odd_depth=0.02, even_depth=0.01, noise=1e-5)
    signal = sig(period_days=PERIOD, epoch=EPOCH, duration_hours=DURATION_DAYS * 24)
    ev = check_odd_even_depth(signal, time, flux)

    assert ev[0].payload["assessed"] is True
    assert ev[0].payload["odd_even_significant"] is True
    assert ev[0].payload["odd_depth_ppm"] == pytest.approx(20_000, rel=0.05)
    assert ev[0].payload["even_depth_ppm"] == pytest.approx(10_000, rel=0.05)
    assert "eclipsing binary" in ev[0].summary


def test_equal_depths_are_not_significant():
    """A real, constant-depth transit: odd and even transits agree."""
    time, flux = folded_light_curve(n_cycles=8, odd_depth=0.01, even_depth=0.01, noise=1e-5)
    signal = sig(period_days=PERIOD, epoch=EPOCH, duration_hours=DURATION_DAYS * 24)
    ev = check_odd_even_depth(signal, time, flux)

    assert ev[0].payload["assessed"] is True
    assert ev[0].payload["odd_even_significant"] is False


def test_zero_noise_with_a_real_difference_is_maximally_significant():
    """Zero within-group scatter is not 'no evidence' - a real mean
    difference with nothing to explain it away is unbounded confidence, not
    a silent pass."""
    time, flux = folded_light_curve(n_cycles=6, odd_depth=0.02, even_depth=0.01, noise=0.0)
    signal = sig(period_days=PERIOD, epoch=EPOCH, duration_hours=DURATION_DAYS * 24)
    ev = check_odd_even_depth(signal, time, flux)

    assert ev[0].payload["odd_even_significant"] is True
    assert ev[0].payload["odd_even_sigma"] == float("inf")


# --- the minimum-transits-per-group gate ----------------------------------------


def test_too_few_transits_per_group_is_not_assessed_not_a_weak_verdict():
    """Fewer than MIN_TRANSITS_PER_GROUP usable transits in either parity
    group: no verdict, not a weak one."""
    n_cycles = MIN_TRANSITS_PER_GROUP  # e.g. 3 total -> 2 of one parity, 1 of the other
    time, flux = folded_light_curve(n_cycles=n_cycles, odd_depth=0.03, even_depth=0.01, noise=1e-5)
    signal = sig(period_days=PERIOD, epoch=EPOCH, duration_hours=DURATION_DAYS * 24)
    ev = check_odd_even_depth(signal, time, flux)

    assert ev[0].payload["assessed"] is False
    assert "odd_even_significant" not in ev[0].payload
    assert ev[0].payload["minimum_required_per_group"] == MIN_TRANSITS_PER_GROUP


def test_exactly_the_minimum_per_group_is_assessed():
    n_cycles = MIN_TRANSITS_PER_GROUP * 2
    time, flux = folded_light_curve(n_cycles=n_cycles, odd_depth=0.02, even_depth=0.01, noise=1e-5)
    signal = sig(period_days=PERIOD, epoch=EPOCH, duration_hours=DURATION_DAYS * 24)
    ev = check_odd_even_depth(signal, time, flux)

    assert ev[0].payload["assessed"] is True
    assert ev[0].payload["odd_transits"] >= MIN_TRANSITS_PER_GROUP
    assert ev[0].payload["even_transits"] >= MIN_TRANSITS_PER_GROUP


# --- absence of an ephemeris/duration is not a clean result --------------------


def test_missing_ephemeris_is_not_assessed():
    signal = sig(duration_hours=2.4)
    ev = check_odd_even_depth(signal, np.array([1.0]), np.array([1.0]))
    assert ev[0].payload == {"assessed": False}


def test_missing_duration_is_not_assessed():
    signal = sig(period_days=PERIOD, epoch=EPOCH)
    ev = check_odd_even_depth(signal, np.array([1.0]), np.array([1.0]))
    assert ev[0].payload == {"assessed": False}
