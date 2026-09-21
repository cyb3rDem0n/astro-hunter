"""Wiring `instrumental.check_instrumental` to the on-disk light-curve cache
(D-041). No network: the light curve itself is a stand-in exposing only what
`check_instrumental_coincidence` reads, the same monkeypatch style already
used for the other archive checks (see `test_mcp_server.py`).
"""

from types import SimpleNamespace

import numpy as np
import pytest

from astro_hunter.core.evidence import derive_verdict
from astro_hunter.core.models import Dossier, Signal, Verdict
from astro_hunter.domains.exoplanets.photometry import tess

POS = {"ra_deg": 84.29928, "dec_deg": -80.464604}
CADENCE = 120 / 86400  # 2 minutes, in days


def sig(**kw):
    return Signal(signal_id="X.01", source="test", target_id="TIC 12345", **POS, **kw)


def observing_record(days=27.4, gaps=()):
    t = np.arange(0.0, days, CADENCE)
    for start, end in gaps:
        t = t[(t < start) | (t > end)]
    return t


class FakeLightCurve:
    """Exposes only `.time.value` and `["quality"].value` - what the glue reads."""

    def __init__(self, time, quality=None):
        self._time = np.asarray(time, dtype=float)
        self._quality = None if quality is None else np.asarray(quality)
        self.colnames = ["time", "flux"] + (["quality"] if quality is not None else [])

    @property
    def time(self):
        return SimpleNamespace(value=self._time)

    def __getitem__(self, key):
        if key == "quality" and self._quality is not None:
            return SimpleNamespace(value=self._quality)
        raise KeyError(key)


# --- cached_2min_sectors --------------------------------------------------------

def test_cached_sectors_are_read_from_disk_not_queried(tmp_path):
    tic_dir = tmp_path / "TIC12345"
    tic_dir.mkdir()
    (tic_dir / "sector014_spoc_120s.fits").touch()
    (tic_dir / "sector027_spoc_120s.fits").touch()
    assert tess.cached_2min_sectors("TIC 12345", tmp_path) == [14, 27]


def test_cached_sectors_empty_when_never_downloaded(tmp_path):
    assert tess.cached_2min_sectors("TIC 99999", tmp_path) == []


def test_cached_sectors_ignores_unrelated_files(tmp_path):
    tic_dir = tmp_path / "TIC12345"
    tic_dir.mkdir()
    (tic_dir / "sector014_spoc_120s.fits").touch()
    (tic_dir / "notes.txt").touch()
    assert tess.cached_2min_sectors("TIC 12345", tmp_path) == [14]


# --- check_instrumental_coincidence: safe non-assessment -----------------------

def test_no_target_id_is_not_assessed(tmp_path):
    signal = Signal(signal_id="X.01", source="test", **POS)
    ev = tess.check_instrumental_coincidence(signal, tmp_path)
    assert len(ev) == 1
    assert ev[0].payload["assessed"] is False


def test_no_2min_product_is_not_assessed_and_not_downloaded(tmp_path, monkeypatch):
    """The 10-of-54 baseline case: MAST confirms nothing exists at 2-minute
    cadence, and no download is attempted."""
    monkeypatch.setattr(tess, "spoc_2min_sectors", lambda target: [])

    def fail(*a, **k):
        raise AssertionError("must not attempt a download with no sector available")

    monkeypatch.setattr(tess, "get_cached_lightcurve", fail)

    signal = sig(period_days=6.27, epoch=1.5, duration_hours=2.8)
    ev = tess.check_instrumental_coincidence(signal, tmp_path)

    assert len(ev) == 1
    assert ev[0].payload["assessed"] is False
    assert ev[0].payload["available_2min"] is False


def test_absent_cadence_evidence_does_not_drive_a_verdict(tmp_path, monkeypatch):
    """Absence of a light curve must not be read as absence of an artefact:
    this evidence alone must not make derive_verdict return INSTRUMENTAL or
    INSUFFICIENT."""
    monkeypatch.setattr(tess, "spoc_2min_sectors", lambda target: [])

    signal = sig(period_days=6.27, epoch=1.5, duration_hours=2.8)
    ev = tess.check_instrumental_coincidence(signal, tmp_path)

    dossier = Dossier(signal=signal, evidence=ev)
    verdict, _, _ = derive_verdict(dossier)
    assert verdict not in (Verdict.INSTRUMENTAL, Verdict.INSUFFICIENT)


def test_mast_unavailable_propagates_as_a_check_failure(tmp_path, monkeypatch):
    """A transient MAST outage is not the same thing as 'no product exists' -
    it must propagate uncaught, like every other archive check's failure."""

    def down(target):
        raise tess.MastUnavailable("MAST did not answer after 3 attempt(s)")

    monkeypatch.setattr(tess, "spoc_2min_sectors", down)

    signal = sig(period_days=6.27, epoch=1.5, duration_hours=2.8)
    with pytest.raises(tess.MastUnavailable):
        tess.check_instrumental_coincidence(signal, tmp_path)


# --- check_instrumental_coincidence: cache hit ----------------------------------

def test_a_cached_sector_is_read_without_touching_mast(tmp_path, monkeypatch):
    tic_dir = tmp_path / "TIC12345"
    tic_dir.mkdir()
    (tic_dir / "sector014_spoc_120s.fits").touch()

    t = observing_record()
    fake_lc = FakeLightCurve(t, quality=np.zeros(len(t), dtype=int))
    monkeypatch.setattr(tess, "get_cached_lightcurve", lambda *a, **k: (None, fake_lc))

    def fail(*a, **k):
        raise AssertionError("must not query MAST when a sector is already cached")

    monkeypatch.setattr(tess, "spoc_2min_sectors", fail)

    signal = sig(period_days=6.27, epoch=1.5, duration_hours=2.8)
    ev = tess.check_instrumental_coincidence(signal, tmp_path)

    assert ev[0].payload["assessed"] is True
    assert ev[0].payload["observed_transits"] == ev[0].payload["predicted_transits"]
    assert not any(e.payload.get("downloaded_during_check") for e in ev)


def test_quality_flags_reach_the_underlying_check(tmp_path, monkeypatch):
    t = observing_record()
    quality = np.zeros(len(t), dtype=int)
    for n in range(6):
        mid = 1.5 + n * 6.27
        quality[(t > mid - 0.1) & (t < mid + 0.1)] = 4096  # Q.Straylight
    fake_lc = FakeLightCurve(t, quality=quality)
    monkeypatch.setattr(tess, "cached_2min_sectors", lambda *a, **k: [14])
    monkeypatch.setattr(tess, "get_cached_lightcurve", lambda *a, **k: (None, fake_lc))

    signal = sig(period_days=6.27, epoch=1.5, duration_hours=2.8)
    ev = tess.check_instrumental_coincidence(signal, tmp_path)

    assert any("spacecraft-event flag" in e.summary for e in ev)


def test_missing_quality_column_is_passed_through_as_none(tmp_path, monkeypatch):
    t = observing_record()
    fake_lc = FakeLightCurve(t, quality=None)
    monkeypatch.setattr(tess, "cached_2min_sectors", lambda *a, **k: [14])
    monkeypatch.setattr(tess, "get_cached_lightcurve", lambda *a, **k: (None, fake_lc))

    signal = sig(period_days=6.27, epoch=1.5, duration_hours=2.8)
    ev = tess.check_instrumental_coincidence(signal, tmp_path)

    assert ev[0].payload["quality_flags_available"] is False


# --- check_instrumental_coincidence: uncached but available ---------------------

def test_an_uncached_sector_is_downloaded_and_the_download_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(tess, "spoc_2min_sectors", lambda target: [14])

    t = observing_record()
    fake_lc = FakeLightCurve(t, quality=np.zeros(len(t), dtype=int))
    monkeypatch.setattr(tess, "get_cached_lightcurve", lambda *a, **k: (None, fake_lc))

    signal = sig(period_days=6.27, epoch=1.5, duration_hours=2.8)
    ev = tess.check_instrumental_coincidence(signal, tmp_path)

    downloaded = [e for e in ev if e.payload.get("downloaded_during_check")]
    assert len(downloaded) == 1
    assert downloaded[0].payload["sector"] == 14
    assert "downloaded from MAST" in downloaded[0].summary


def test_a_cached_sector_never_reports_a_download(tmp_path, monkeypatch):
    tic_dir = tmp_path / "TIC12345"
    tic_dir.mkdir()
    (tic_dir / "sector014_spoc_120s.fits").touch()

    t = observing_record()
    fake_lc = FakeLightCurve(t, quality=np.zeros(len(t), dtype=int))
    monkeypatch.setattr(tess, "get_cached_lightcurve", lambda *a, **k: (None, fake_lc))

    signal = sig(period_days=6.27, epoch=1.5, duration_hours=2.8)
    ev = tess.check_instrumental_coincidence(signal, tmp_path)

    assert not any(e.payload.get("downloaded_during_check") for e in ev)


# --- check_odd_even_depth: wiring to download_tess_lightcurve (D-038) ----------
#
# check_odd_even_depth needs flux, not just time/quality, so it goes through
# download_tess_lightcurve rather than the raw get_cached_lightcurve the
# instrumental check reads - monkeypatched as one opaque acquisition step,
# the same boundary the instrumental tests mock at.


class FakeCleanLightCurve:
    """Exposes only `.time.value` and `.flux.value` - what the odd/even glue
    reads from `download_tess_lightcurve`'s cleaned output."""

    def __init__(self, time, flux):
        self._time = np.asarray(time, dtype=float)
        self._flux = np.asarray(flux, dtype=float)

    @property
    def time(self):
        return SimpleNamespace(value=self._time)

    @property
    def flux(self):
        return SimpleNamespace(value=self._flux)


def folded_flux(period, epoch, duration_days, n_cycles, odd_depth, even_depth):
    t_start, t_end = epoch - 0.5, epoch + (n_cycles - 1) * period + 0.5
    t = np.arange(t_start, t_end, CADENCE)
    flux = np.ones_like(t)
    for n in range(n_cycles):
        mid = epoch + n * period
        depth = odd_depth if n % 2 else even_depth
        half = duration_days / 2
        flux[(t >= mid - half) & (t <= mid + half)] -= depth
    return t, flux


def test_odd_even_no_target_id_is_not_assessed(tmp_path):
    signal = Signal(signal_id="X.01", source="test", **POS)
    ev = tess.check_odd_even_depth(signal, tmp_path)
    assert len(ev) == 1
    assert ev[0].payload["assessed"] is False


def test_odd_even_no_2min_product_is_not_assessed_and_not_downloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(tess, "spoc_2min_sectors", lambda target: [])

    def fail(*a, **k):
        raise AssertionError("must not attempt a download with no sector available")

    monkeypatch.setattr(tess, "download_tess_lightcurve", fail)

    signal = sig(period_days=2.0, epoch=1.0, duration_hours=2.4)
    ev = tess.check_odd_even_depth(signal, tmp_path)

    assert ev[0].payload["assessed"] is False
    assert ev[0].payload["available_2min"] is False


def test_odd_even_mast_unavailable_propagates_as_a_check_failure(tmp_path, monkeypatch):
    def down(target):
        raise tess.MastUnavailable("MAST did not answer after 3 attempt(s)")

    monkeypatch.setattr(tess, "spoc_2min_sectors", down)

    signal = sig(period_days=2.0, epoch=1.0, duration_hours=2.4)
    with pytest.raises(tess.MastUnavailable):
        tess.check_odd_even_depth(signal, tmp_path)


def test_odd_even_a_cached_sector_is_read_without_touching_mast(tmp_path, monkeypatch):
    tic_dir = tmp_path / "TIC12345"
    tic_dir.mkdir()
    (tic_dir / "sector014_spoc_120s.fits").touch()

    t, flux = folded_flux(2.0, 1.0, 0.1, n_cycles=8, odd_depth=0.02, even_depth=0.01)
    fake_clean = FakeCleanLightCurve(t, flux)
    monkeypatch.setattr(
        tess, "download_tess_lightcurve", lambda *a, **k: (None, None, fake_clean)
    )

    def fail(*a, **k):
        raise AssertionError("must not query MAST when a sector is already cached")

    monkeypatch.setattr(tess, "spoc_2min_sectors", fail)

    signal = sig(period_days=2.0, epoch=1.0, duration_hours=2.4)
    ev = tess.check_odd_even_depth(signal, tmp_path)

    assert ev[0].payload["assessed"] is True
    assert ev[0].payload["odd_even_significant"] is True
    assert not any(e.payload.get("downloaded_during_check") for e in ev)


def test_odd_even_an_uncached_sector_is_downloaded_and_the_download_is_recorded(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tess, "spoc_2min_sectors", lambda target: [14])

    t, flux = folded_flux(2.0, 1.0, 0.1, n_cycles=8, odd_depth=0.02, even_depth=0.01)
    fake_clean = FakeCleanLightCurve(t, flux)
    monkeypatch.setattr(
        tess, "download_tess_lightcurve", lambda *a, **k: (None, None, fake_clean)
    )

    signal = sig(period_days=2.0, epoch=1.0, duration_hours=2.4)
    ev = tess.check_odd_even_depth(signal, tmp_path)

    downloaded = [e for e in ev if e.payload.get("downloaded_during_check")]
    assert len(downloaded) == 1
    assert downloaded[0].payload["sector"] == 14
