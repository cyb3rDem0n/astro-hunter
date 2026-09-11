"""The TOI queue: row parsing, mode separation, and the label boundary."""

import math

import pytest

from astro_hunter.sources import toi
from astro_hunter.sources.toi import (
    BTJD_OFFSET,
    DISPOSITION_COLUMN,
    QueueUnavailable,
    fetch_triage_queue,
    load_benchmark,
    signal_from_row,
    write_benchmark,
)


class FakeRow:
    """Mimics an astropy row: iterable, with colnames."""

    def __init__(self, data):
        self._data = data
        self.colnames = list(data)

    def __iter__(self):
        return iter(self._data.values())


class FakeService:
    def __init__(self, rows=None, error=None):
        self._rows = [FakeRow(r) for r in (rows or [])]
        self._error = error
        self.last_query = None

    def search(self, adql):
        self.last_query = adql
        if self._error:
            raise RuntimeError(self._error)
        return self

    def to_table(self):
        return self._rows


def row(**kw):
    base = {"toi": 144.01, "tid": 261136679, "ra": 84.29928, "dec": -80.464604,
            "pl_orbper": 6.2678139, "pl_tranmid": 2458325.5, "pl_trandep": 321.0,
            "pl_trandurh": 2.789}
    base.update(kw)
    return base


# --- row parsing --------------------------------------------------------------

def test_a_row_becomes_a_signal():
    s = signal_from_row(row())
    assert s.signal_id == "TOI-144.01"
    assert s.target_id == "TIC 261136679"
    assert s.period_days == pytest.approx(6.2678139)
    assert s.depth_ppm == pytest.approx(321.0)


def test_epoch_is_converted_to_btjd():
    """Light-curve timestamps are BTJD; the catalog records BJD. Mixing them
    displaces an ephemeris by 2457000 days, which reads as a missing transit
    rather than as an error."""
    s = signal_from_row(row(pl_tranmid=2458325.5))
    assert s.epoch == pytest.approx(2458325.5 - BTJD_OFFSET)
    assert 0 < s.epoch < 5000


def test_missing_values_become_none_not_nan():
    s = signal_from_row(row(pl_orbper=None, pl_trandep=float("nan")))
    assert s.period_days is None
    assert s.depth_ppm is None


def test_a_row_without_an_epoch_has_no_epoch():
    s = signal_from_row(row(pl_tranmid=None))
    assert s.epoch is None


def test_a_row_without_a_position_is_rejected():
    with pytest.raises((KeyError, TypeError, ValueError)):
        signal_from_row(row(ra=None))


# --- mode separation ----------------------------------------------------------

def test_the_triage_query_never_names_the_disposition():
    """D-016: the column is absent from the SELECT, so no label exists to leak."""
    service = FakeService([row()])
    fetch_triage_queue(limit=5, service=service)
    assert DISPOSITION_COLUMN not in service.last_query


def test_triage_signals_carry_no_label():
    signals = fetch_triage_queue(limit=5, service=FakeService([row()]))
    assert all(not hasattr(s, "disposition") for s in signals)
    assert all(DISPOSITION_COLUMN not in s.extra for s in signals)


def test_rows_that_cannot_be_parsed_are_skipped_not_fatal():
    service = FakeService([row(), row(ra=None), row(toi=145.01)])
    signals = fetch_triage_queue(limit=10, service=service)
    assert len(signals) == 2


def test_an_unreachable_catalog_raises():
    with pytest.raises(QueueUnavailable):
        fetch_triage_queue(service=FakeService(error="refused"))


# --- pinned benchmark ---------------------------------------------------------

def test_benchmark_round_trips_through_the_file(tmp_path):
    sample = [(signal_from_row(row()), "CP"),
              (signal_from_row(row(toi=200.01, pl_orbper=None)), "FP")]
    path = tmp_path / "bench.csv"
    write_benchmark(sample, path)

    loaded = load_benchmark(path)
    assert [label for _s, label in loaded] == ["CP", "FP"]
    assert loaded[0][0].period_days == pytest.approx(6.2678139)
    assert loaded[1][0].period_days is None


def test_labels_come_back_separate_from_signals(tmp_path):
    """Handing a disposition to a check must require writing it out."""
    path = tmp_path / "bench.csv"
    write_benchmark([(signal_from_row(row()), "KP")], path)
    signal, label = load_benchmark(path)[0]
    assert label == "KP"
    assert "KP" not in str(signal)


def test_epoch_survives_the_round_trip(tmp_path):
    path = tmp_path / "bench.csv"
    original = signal_from_row(row())
    write_benchmark([(original, "CP")], path)
    restored, _ = load_benchmark(path)[0]
    assert restored.epoch == pytest.approx(original.epoch)


def test_the_sample_is_stratified(monkeypatch):
    """Uniform sampling would be 59 % planet candidates and would barely see
    false alarms, which are 1.2 % of the catalog."""
    rows = ([row(toi=float(i), pl_orbper=3.0) | {"tfopwg_disp": "PC"}
             for i in range(500)]
            + [row(toi=1000.0 + i) | {"tfopwg_disp": "FA"} for i in range(5)])
    sample = toi.fetch_benchmark_sample(per_class=10, service=FakeService(rows))
    counts = {}
    for _s, label in sample:
        counts[label] = counts.get(label, 0) + 1
    assert counts == {"PC": 10, "FA": 5}


def test_sampling_is_reproducible(monkeypatch):
    rows = [row(toi=float(i)) | {"tfopwg_disp": "PC"} for i in range(200)]
    a = toi.fetch_benchmark_sample(per_class=20, seed=7, service=FakeService(rows))
    b = toi.fetch_benchmark_sample(per_class=20, seed=7, service=FakeService(rows))
    assert [s.signal_id for s, _ in a] == [s.signal_id for s, _ in b]


def test_a_different_seed_gives_a_different_sample():
    rows = [row(toi=float(i)) | {"tfopwg_disp": "PC"} for i in range(200)]
    a = toi.fetch_benchmark_sample(per_class=20, seed=1, service=FakeService(rows))
    b = toi.fetch_benchmark_sample(per_class=20, seed=2, service=FakeService(rows))
    assert [s.signal_id for s, _ in a] != [s.signal_id for s, _ in b]


def test_unlabelled_rows_are_excluded(monkeypatch):
    rows = [row(toi=1.01) | {"tfopwg_disp": "PC"},
            row(toi=2.01) | {"tfopwg_disp": None},
            row(toi=3.01) | {"tfopwg_disp": "  "}]
    sample = toi.fetch_benchmark_sample(per_class=10, service=FakeService(rows))
    assert len(sample) == 1


def test_no_value_is_nan_after_loading(tmp_path):
    path = tmp_path / "bench.csv"
    write_benchmark([(signal_from_row(row(pl_trandep=float("nan"))), "PC")], path)
    signal, _ = load_benchmark(path)[0]
    for value in (signal.period_days, signal.epoch, signal.depth_ppm):
        assert value is None or not math.isnan(value)


def test_a_masked_value_becomes_none_without_a_warning():
    """Regression: astropy table cells for missing data are numpy masked
    elements, not None. float() on one succeeds and returns nan with a
    UserWarning - correct after nan-filtering, but noisy, and a mask that
    reached code without nan-filtering would be a silent defect."""
    import warnings

    from numpy import ma

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert toi._number(ma.masked) is None
        assert toi._number(ma.array([1.0], mask=[True])[0]) is None


def test_a_masked_row_value_is_handled_in_signal_from_row():
    from numpy import ma

    r = row(pl_orbper=ma.array([1.0], mask=[True])[0])
    s = signal_from_row(r)
    assert s.period_days is None
