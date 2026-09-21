"""Odd/even transit-depth comparison.

Evidence path for `FP` (D-017, D-038): the actual `EXPLAINED` check D-038
identified and left open. An eclipsing binary at the true orbital period
produces a primary and a secondary eclipse of different depths; a blind
period search that locks onto half that period sees one constant-looking
periodic dip and cannot tell it apart from a real, constant-depth transit
without folding separately on odd- and even-numbered transits and comparing.

Unlike the catalog modules, this one queries nothing once handed a light
curve's own time and flux arrays - the acquisition side
(`photometry/tess.py`) resolves the cached product; this stays
acquisition-free, the same split `instrumental.py` already uses.

The local baseline (not a global flatten) is deliberate: D-004/D-009, the
open questions about global detrending parameters and outlier-rejection
ordering, are not resolved here, on purpose (CLAUDE.md - a disagreement or
an open scientific decision is not this check's call to make). A baseline
window a few transit durations wide, drawn fresh around each transit, does
not depend on whichever global method D-004/D-009 eventually settles on.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from astro_hunter.core.models import Evidence, EvidenceKind
from astro_hunter.domains.exoplanets.instrumental import predicted_transit_times

SOURCE = "light curve (odd/even depth)"

# A group's mean depth and spread mean nothing below this many usable
# transits: two points give one degree of freedom for the spread, too
# unstable to trust a significance call on. Three is the practical floor for
# a non-degenerate sample variance - below it, this check reports
# `assessed: False` rather than a weak significant/not-significant verdict.
MIN_TRANSITS_PER_GROUP = 3

# How far from a transit's centre, in units of the transit duration, its own
# local out-of-transit baseline is drawn from - wide enough for a stable
# mean, close enough in time to be insensitive to any global trend.
LOCAL_BASELINE_DURATIONS = 3.0

# Odd/even significance convention: the same odd-even depth test TESS/Kepler
# Data Validation reports already run, at the same order of magnitude for
# "distinguishable from noise." A difference below this many combined
# standard errors is not called significant.
SIGNIFICANCE_SIGMA = 3.0


def _transit_depth(time: np.ndarray, flux: np.ndarray, mid: float, duration_days: float) -> float | None:
    """One transit's depth in ppm, against its own local out-of-transit
    baseline. `None` if either window has too few points to be usable.
    """
    half = duration_days / 2.0
    span = duration_days * LOCAL_BASELINE_DURATIONS
    in_transit = (time >= mid - half) & (time <= mid + half)
    baseline = (
        ((time >= mid - span) & (time < mid - half))
        | ((time > mid + half) & (time <= mid + span))
    )
    n_in, n_out = int(np.count_nonzero(in_transit)), int(np.count_nonzero(baseline))
    if n_in < 1 or n_out < 2:
        return None

    baseline_mean = float(np.mean(flux[baseline]))
    if baseline_mean == 0:
        return None
    in_mean = float(np.mean(flux[in_transit]))
    return (baseline_mean - in_mean) / baseline_mean * 1e6


def check_odd_even_depth(signal, time, flux) -> list[Evidence]:
    """Fold on the signal's own period, split transits by parity, compare
    mean depth per group.

    `time` and `flux` are the light curve's own arrays (cleaned - NaNs
    removed, a flux column selected - by the acquisition side, the same
    split `check_instrumental_coincidence`/`instrumental.check_instrumental`
    already use for time/quality).
    """
    retrieved = datetime.now(UTC)

    if not signal.period_days or signal.epoch is None:
        return [Evidence(
            kind=EvidenceKind.DERIVED,
            source=SOURCE,
            summary="no ephemeris on the signal; odd/even depth not assessable",
            retrieved_at=retrieved,
            payload={"assessed": False},
        )]

    duration_days = (signal.duration_hours / 24.0) if signal.duration_hours else None
    if duration_days is None:
        return [Evidence(
            kind=EvidenceKind.DERIVED,
            source=SOURCE,
            summary="no transit duration available; odd/even depth not assessable",
            retrieved_at=retrieved,
            payload={"assessed": False},
        )]

    time = np.asarray(time, dtype=float)
    flux = np.asarray(flux, dtype=float)
    t_start, t_end = float(time.min()), float(time.max())
    predicted = predicted_transit_times(signal.epoch, signal.period_days, t_start, t_end)

    odd_depths: list[float] = []
    even_depths: list[float] = []
    for mid in predicted:
        depth = _transit_depth(time, flux, mid, duration_days)
        if depth is None:
            continue
        cycle = round((mid - signal.epoch) / signal.period_days)
        (odd_depths if cycle % 2 else even_depths).append(depth)

    if len(odd_depths) < MIN_TRANSITS_PER_GROUP or len(even_depths) < MIN_TRANSITS_PER_GROUP:
        return [Evidence(
            kind=EvidenceKind.DERIVED,
            source=SOURCE,
            summary=(
                f"only {len(odd_depths)} odd and {len(even_depths)} even transit(s) "
                f"with a usable local baseline - below the {MIN_TRANSITS_PER_GROUP} "
                f"needed per group for a significance test"
            ),
            retrieved_at=retrieved,
            payload={
                "assessed": False,
                "odd_transits": len(odd_depths),
                "even_transits": len(even_depths),
                "minimum_required_per_group": MIN_TRANSITS_PER_GROUP,
            },
        )]

    odd_mean, even_mean = float(np.mean(odd_depths)), float(np.mean(even_depths))
    odd_se = float(np.std(odd_depths, ddof=1) / np.sqrt(len(odd_depths)))
    even_se = float(np.std(even_depths, ddof=1) / np.sqrt(len(even_depths)))
    combined_se = float(np.hypot(odd_se, even_se))
    if combined_se > 0:
        sigma = abs(odd_mean - even_mean) / combined_se
    else:
        # Zero scatter within both groups is not "no evidence" - with a real
        # mean difference and no measurement noise to explain it, confidence
        # is unbounded, not zero.
        sigma = float("inf") if odd_mean != even_mean else 0.0
    significant = sigma >= SIGNIFICANCE_SIGMA

    verdict_phrase = (
        "consistent with an eclipsing binary at twice the search period"
        if significant else "not a significant difference"
    )
    summary = (
        f"odd-transit depth {odd_mean:.0f} ppm vs even-transit depth {even_mean:.0f} ppm "
        f"({len(odd_depths)} vs {len(even_depths)} transits): {sigma:.1f}-sigma, {verdict_phrase}"
    )

    return [Evidence(
        kind=EvidenceKind.DERIVED,
        source=SOURCE,
        summary=summary,
        retrieved_at=retrieved,
        payload={
            "assessed": True,
            "odd_depth_ppm": round(odd_mean, 1),
            "even_depth_ppm": round(even_mean, 1),
            "odd_transits": len(odd_depths),
            "even_transits": len(even_depths),
            "odd_even_sigma": round(sigma, 2),
            "odd_even_significant": significant,
        },
    )]
