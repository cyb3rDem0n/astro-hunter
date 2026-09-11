"""The TOI catalog as a queue source.

Two modes, kept apart in code rather than by discipline (D-016).

**Triage** builds signals for assessment. The disposition column is never named
in the query, so a label cannot reach the agent even by accident.

**Benchmark** reads a committed sample in which dispositions are retained as
hidden labels. Loading returns signals and labels as separate objects, so
passing a labelled row to a check requires an explicit, visible mistake.

The benchmark sample is a file in the repository, not a live query (D-015).
Dispositions are revised as follow-up accumulates, so evaluating against the
live catalog would compare today's verdicts to labels that have moved. A
refresh is a deliberate commit with a new date.
"""

from __future__ import annotations

import csv
import math
import random
from pathlib import Path

import numpy as np
import pyvo

from astro_hunter.core.http import tap_service
from astro_hunter.core.models import Signal

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP"
TABLE = "toi"
DISPOSITION_COLUMN = "tfopwg_disp"

# Selected explicitly. A SELECT * would pull ninety columns, and in triage mode
# would pull the disposition along with them.
SIGNAL_COLUMNS = (
    "toi", "tid", "ra", "dec",
    "pl_orbper", "pl_tranmid", "pl_trandep", "pl_trandurh",
)

# BTJD = BJD - 2457000. TESS light-curve timestamps are BTJD; the catalog
# records mid-transit in BJD. Mixing them displaces an ephemeris by four and a
# half thousand days, which reads as a missing transit rather than as an error.
BTJD_OFFSET = 2_457_000.0


class QueueUnavailable(RuntimeError):
    """The catalog could not be reached."""


def _service() -> pyvo.dal.TAPService:
    """A service that times out rather than hanging. See core.http."""
    return tap_service(TAP_URL)


def _number(value):
    """A clean float, or None for anything that is not one.

    astropy table cells for missing data are numpy masked elements, not None.
    ``float()`` on a masked element succeeds and returns nan, with a UserWarning
    on every call - correct in the end since nan is filtered below, but noisy,
    and a masked element reaching code that does not filter nan would be a
    silent defect rather than this warning. Checking the mask explicitly avoids
    both.
    """
    if value is None:
        return None
    if getattr(value, "mask", False) is True or value is np.ma.masked:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def signal_from_row(row, source: str = "toi") -> Signal:
    """Build a Signal from a TOI row.

    Epoch is converted from BJD to BTJD so it can be compared against light
    curve timestamps without a further conversion at the point of use.
    """
    epoch_bjd = _number(row.get("pl_tranmid"))
    toi = row.get("toi")
    return Signal(
        signal_id=f"TOI-{toi}" if toi is not None else str(row.get("tid")),
        source=source,
        ra_deg=float(row["ra"]),
        dec_deg=float(row["dec"]),
        period_days=_number(row.get("pl_orbper")),
        epoch=None if epoch_bjd is None else epoch_bjd - BTJD_OFFSET,
        depth_ppm=_number(row.get("pl_trandep")),
        duration_hours=_number(row.get("pl_trandurh")),
        target_id=None if row.get("tid") is None else f"TIC {row['tid']}",
    )


def fetch_triage_queue(limit: int = 50, service=None) -> list[Signal]:
    """Signals awaiting assessment. The disposition is not queried.

    The column is absent from the SELECT, so no label exists to leak, whatever
    happens downstream.
    """
    adql = f"SELECT TOP {int(limit)} {', '.join(SIGNAL_COLUMNS)} FROM {TABLE}"
    if DISPOSITION_COLUMN in adql:
        raise AssertionError("triage query must not reference the disposition column")
    try:
        rows = (service or _service()).search(adql).to_table()
    except Exception as exc:
        raise QueueUnavailable(f"TOI query failed: {exc}") from exc

    signals = []
    for r in rows:
        try:
            signals.append(signal_from_row(dict(zip(r.colnames, r, strict=False))))
        except (KeyError, TypeError, ValueError):
            continue                          # a row without a position is not a signal
    return signals


def fetch_benchmark_sample(
    per_class: int = 100,
    seed: int = 20260911,
    service=None,
) -> list[tuple[Signal, str]]:
    """A stratified sample with its labels, for writing to a pinned file.

    Stratified because the classes are heavily imbalanced: a uniform sample
    would be 59 % planet candidates and would barely see false alarms, which are
    1.2 % of the catalog. Equal numbers per class make per-class precision and
    recall meaningful, and the majority-class baseline is computed from the
    catalog's real proportions rather than from the sample's.
    """
    columns = ", ".join((*SIGNAL_COLUMNS, DISPOSITION_COLUMN))
    adql = f"""
        SELECT {columns}
        FROM {TABLE}
        WHERE {DISPOSITION_COLUMN} IS NOT NULL
          AND ra IS NOT NULL AND dec IS NOT NULL
    """
    try:
        rows = (service or _service()).search(adql).to_table()
    except Exception as exc:
        raise QueueUnavailable(f"TOI query failed: {exc}") from exc

    by_class: dict[str, list[dict]] = {}
    for r in rows:
        record = dict(zip(r.colnames, r, strict=False))
        label = str(record.get(DISPOSITION_COLUMN) or "").strip()
        if label:
            by_class.setdefault(label, []).append(record)

    rng = random.Random(seed)
    sample = []
    for label in sorted(by_class):
        rows_for_label = by_class[label]
        chosen = rng.sample(rows_for_label, min(per_class, len(rows_for_label)))
        for record in chosen:
            try:
                sample.append((signal_from_row(record, source="toi-benchmark"), label))
            except (KeyError, TypeError, ValueError):
                continue
    return sample


BENCHMARK_FIELDS = (
    "signal_id", "target_id", "ra_deg", "dec_deg",
    "period_days", "epoch_btjd", "depth_ppm", "duration_hours", "disposition",
)


def write_benchmark(sample: list[tuple[Signal, str]], path: Path) -> None:
    """Persist a sample so results are reproducible against a fixed label set."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=BENCHMARK_FIELDS)
        writer.writeheader()
        for signal, label in sample:
            writer.writerow({
                "signal_id": signal.signal_id,
                "target_id": signal.target_id or "",
                "ra_deg": signal.ra_deg,
                "dec_deg": signal.dec_deg,
                "period_days": signal.period_days if signal.period_days else "",
                "epoch_btjd": signal.epoch if signal.epoch is not None else "",
                "depth_ppm": signal.depth_ppm if signal.depth_ppm else "",
                "duration_hours": signal.duration_hours if signal.duration_hours else "",
                "disposition": label,
            })


def load_benchmark(path: Path) -> list[tuple[Signal, str]]:
    """Read the pinned sample. Signals and labels come back separate.

    Returning a pair rather than a labelled object means handing a disposition
    to a check requires writing it out, which is visible in review.
    """
    out = []
    with Path(path).open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            signal = Signal(
                signal_id=row["signal_id"],
                source="toi-benchmark",
                ra_deg=float(row["ra_deg"]),
                dec_deg=float(row["dec_deg"]),
                period_days=_number(row["period_days"] or None),
                epoch=_number(row["epoch_btjd"] or None),
                depth_ppm=_number(row["depth_ppm"] or None),
                duration_hours=_number(row["duration_hours"] or None),
                target_id=row["target_id"] or None,
            )
            out.append((signal, row["disposition"]))
    return out
