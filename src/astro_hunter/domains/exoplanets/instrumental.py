"""Instrumental artefact checks.

Evidence path for `FA` (D-017). Unlike the catalog modules, this one queries
nothing: the information lives in the light curve the signal came from, as
timestamps and quality flags. A blind period search knows nothing about the
spacecraft, so a periodicity in the *observing pattern* is indistinguishable to
it from a periodicity in the star.

Three failure modes are checked, and they are different questions.

**Coincidence with flagged cadences.** SPOC marks cadences affected by
momentum dumps, scattered light, Earth pointing and attitude tweaks. A signal
whose transits sit preferentially on flagged cadences is following the
spacecraft, not the star.

**Coincidence with gaps.** Data gaps are periodic — orbit downlinks, sector
boundaries — so a search can lock onto a period that places its transits inside
them. Such a period is an alias of the observing window, and the giveaway is
that the "transits" are largely unobserved.

**Insufficient coverage.** A period claimed from one or two partially covered
events is not established, whatever the periodogram says. Counting events with
real coverage is separate from counting events the ephemeris predicts.

None of this proves a signal is real. It identifies signals that are explained
by the instrument, which is a different and much cheaper thing.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from lightkurve.utils import TessQualityFlags as Q

from astro_hunter.core.models import Evidence, EvidenceKind

# Flags that make a cadence untrustworthy for transit detection. Cosmic rays and
# impulsive outliers are excluded: they are single-cadence events that outlier
# rejection already removes, and counting them here would flag healthy data.
SUSPICIOUS_FLAGS = (
    Q.AttitudeTweak
    | Q.SafeMode
    | Q.CoarsePoint
    | Q.EarthPoint
    | Q.Desat
    | Q.ManualExclude
    | Q.Straylight
    | Q.Straylight2
    | Q.PlanetSearchExclude
    | Q.BadCalibrationExclude
)

MIN_COVERAGE = 0.5           # below this, a predicted transit counts as unobserved
MIN_OBSERVED_TRANSITS = 2    # one event defines no period
FLAGGED_FRACTION_ALERT = 0.3


def median_cadence(time: np.ndarray) -> float:
    """Typical spacing between samples, in the units of ``time``.

    The median rather than the mean: gaps are large and few, and would drag a
    mean upwards until the expected-sample count became meaningless.
    """
    if len(time) < 2:
        raise ValueError("need at least two samples to estimate a cadence")
    return float(np.median(np.diff(np.sort(np.asarray(time, dtype=float)))))


def predicted_transit_times(
    epoch: float, period_days: float, t_start: float, t_end: float
) -> list[float]:
    """Every mid-transit the ephemeris places inside the observed baseline.

    Predicted, not observed. The difference between the two counts is the point
    of this module.
    """
    if period_days <= 0:
        raise ValueError(f"period must be positive, got {period_days}")
    first = int(np.floor((t_start - epoch) / period_days))
    last = int(np.ceil((t_end - epoch) / period_days))
    times = [epoch + n * period_days for n in range(first, last + 1)]
    return [t for t in times if t_start <= t <= t_end]


def assess_transit(
    time: np.ndarray,
    quality: np.ndarray | None,
    mid: float,
    duration_days: float,
    cadence: float,
) -> dict:
    """Coverage and flag status of one predicted transit."""
    half = duration_days / 2.0
    in_window = (time >= mid - half) & (time <= mid + half)
    n_present = int(np.count_nonzero(in_window))
    n_expected = max(1, round(duration_days / cadence))

    if quality is None or n_present == 0:
        n_flagged = 0
    else:
        n_flagged = int(np.count_nonzero(
            np.asarray(quality)[in_window].astype(int) & SUSPICIOUS_FLAGS
        ))

    coverage = min(1.0, n_present / n_expected)
    return {
        "mid_time": round(float(mid), 6),
        "cadences_present": n_present,
        "cadences_expected": n_expected,
        "coverage": round(coverage, 3),
        "cadences_flagged": n_flagged,
        "flagged_fraction": round(n_flagged / n_present, 3) if n_present else 0.0,
        "observed": coverage >= MIN_COVERAGE,
    }


def check_instrumental(
    signal,
    time,
    quality=None,
    duration_days: float | None = None,
) -> list[Evidence]:
    """Assess a signal against the observing record it came from.

    ``time`` and ``quality`` are the light curve's own arrays. ``quality`` may
    be omitted, in which case gaps are still assessed and flags are not —
    reported as such rather than silently treated as clean.
    """
    retrieved = datetime.now(UTC)

    if not signal.period_days or signal.epoch is None:
        return [Evidence(
            kind=EvidenceKind.INSTRUMENTAL_WINDOW,
            source="observing record",
            summary="no ephemeris on the signal; instrumental coincidence not assessable",
            retrieved_at=retrieved,
            payload={"assessed": False},
        )]

    time = np.asarray(time, dtype=float)
    duration = duration_days
    if duration is None:
        duration = (signal.duration_hours / 24.0) if signal.duration_hours else None
    if duration is None:
        return [Evidence(
            kind=EvidenceKind.INSTRUMENTAL_WINDOW,
            source="observing record",
            summary="no transit duration available; coverage not assessable",
            retrieved_at=retrieved,
            payload={"assessed": False},
        )]

    cadence = median_cadence(time)
    t_start, t_end = float(time.min()), float(time.max())
    predicted = predicted_transit_times(signal.epoch, signal.period_days, t_start, t_end)

    per_transit = [
        assess_transit(time, quality, mid, duration, cadence) for mid in predicted
    ]
    observed = [t for t in per_transit if t["observed"]]
    total_present = sum(t["cadences_present"] for t in per_transit)
    total_flagged = sum(t["cadences_flagged"] for t in per_transit)
    flagged_fraction = (total_flagged / total_present) if total_present else 0.0

    evidence = [Evidence(
        kind=EvidenceKind.INSTRUMENTAL_WINDOW,
        source="observing record",
        summary=(
            f"{len(observed)} of {len(predicted)} predicted transits have data "
            f"coverage above {MIN_COVERAGE:.0%}"
        ),
        retrieved_at=retrieved,
        payload={
            "assessed": True,
            "predicted_transits": len(predicted),
            "observed_transits": len(observed),
            "baseline_days": round(t_end - t_start, 4),
            "cadence_days": round(cadence, 8),
            "quality_flags_available": quality is not None,
            "per_transit": per_transit,
        },
    )]

    if len(observed) < MIN_OBSERVED_TRANSITS:
        evidence.append(Evidence(
            kind=EvidenceKind.INSTRUMENTAL_WINDOW,
            source="observing record",
            summary=(
                f"only {len(observed)} transit(s) actually covered by data: "
                f"the period is not established by the observations"
            ),
            retrieved_at=retrieved,
            payload={"observed_transits": len(observed),
                     "minimum_required": MIN_OBSERVED_TRANSITS},
        ))

    if predicted and len(observed) < len(predicted):
        missing = len(predicted) - len(observed)
        evidence.append(Evidence(
            kind=EvidenceKind.INSTRUMENTAL_WINDOW,
            source="observing record",
            summary=(
                f"{missing} predicted transit(s) fall in data gaps; a period "
                f"that places events in gaps may be an alias of the observing window"
            ),
            retrieved_at=retrieved,
            payload={"transits_in_gaps": missing,
                     "predicted_transits": len(predicted)},
        ))

    if quality is not None and flagged_fraction > FLAGGED_FRACTION_ALERT:
        evidence.append(Evidence(
            kind=EvidenceKind.INSTRUMENTAL_WINDOW,
            source="SPOC quality flags",
            summary=(
                f"{flagged_fraction:.0%} of in-transit cadences carry a "
                f"spacecraft-event flag"
            ),
            retrieved_at=retrieved,
            payload={"flagged_fraction": round(flagged_fraction, 3),
                     "flagged_cadences": total_flagged,
                     "in_transit_cadences": total_present,
                     "flag_bitmask": int(SUSPICIOUS_FLAGS)},
        ))

    return evidence
