"""Aperture contamination: the photometry, then the query, then the evidence."""

import pytest

from astro_hunter.core.models import EvidenceKind, Signal
from astro_hunter.domains.exoplanets.neighbours import (
    CatalogUnavailable,
    _cone_predicate,
    corrected_depth,
    crossmatch_neighbours,
    dilution,
    find_neighbours,
    flux_ratio,
    max_depth_from_neighbour,
)

POS = {"ra_deg": 84.29928, "dec_deg": -80.464604}


class FakeService:
    def __init__(self, rows=None, error=None):
        self._rows, self._error = rows or [], error

    def search(self, adql):
        if self._error:
            raise RuntimeError(self._error)
        return self

    def to_table(self):
        return self._rows


def src(ra, dec, g, sid="1"):
    return {"source_id": sid, "ra": ra, "dec": dec, "phot_g_mean_mag": g,
            "parallax": None, "pmra": None, "pmdec": None}


# --- photometry ---------------------------------------------------------------

def test_five_magnitudes_fainter_is_one_percent():
    """The defining property of the magnitude scale."""
    assert flux_ratio(15.0, 10.0) == pytest.approx(0.01)


def test_equal_magnitudes_give_equal_flux():
    assert flux_ratio(12.0, 12.0) == pytest.approx(1.0)


def test_an_empty_aperture_is_undiluted():
    assert dilution([]) == pytest.approx(1.0)


def test_an_equal_brightness_companion_halves_the_target_share():
    assert dilution([1.0]) == pytest.approx(0.5)


def test_dilution_makes_the_measured_depth_too_shallow():
    """An equal companion halves every depth. Undoing it doubles them back."""
    assert corrected_depth(0.001, [1.0]) == pytest.approx(0.002)


def test_correction_is_a_no_op_without_contamination():
    assert corrected_depth(0.00032, []) == pytest.approx(0.00032)


def test_a_neighbour_cannot_remove_more_light_than_it_emits():
    """Upper bound, not an estimate: a total eclipse is the limit case."""
    ratios = [0.01]
    assert max_depth_from_neighbour(0.01, ratios) == pytest.approx(0.01 / 1.01)


def test_a_faint_neighbour_cannot_explain_a_deep_transit():
    """The exclusion that makes this rigorous rather than suggestive.

    A neighbour six magnitudes fainter holds about 0.4 % of the aperture flux,
    so it cannot produce a 1 % dip however it behaves.
    """
    r = flux_ratio(16.0, 10.0)
    assert max_depth_from_neighbour(r, [r]) < 0.01


def test_a_bright_neighbour_can_explain_a_shallow_transit():
    """And the converse: 320 ppm is well within reach of an equal companion."""
    r = flux_ratio(10.2, 10.0)
    assert max_depth_from_neighbour(r, [r]) > 320e-6


# --- query --------------------------------------------------------------------

def test_nearest_source_is_taken_as_the_target():
    rows = [src(POS["ra_deg"] + 0.002, POS["dec_deg"], 14.0, "neighbour"),
            src(POS["ra_deg"], POS["dec_deg"], 10.0, "target")]
    target, neighbours = find_neighbours(**POS, service=FakeService(rows))
    assert target["source_id"] == "target"
    assert [n["source_id"] for n in neighbours] == ["neighbour"]


def test_sources_outside_the_aperture_are_dropped():
    rows = [src(POS["ra_deg"], POS["dec_deg"], 10.0, "target"),
            src(POS["ra_deg"], POS["dec_deg"] + 0.05, 11.0, "far")]   # 180 arcsec
    _, neighbours = find_neighbours(**POS, radius_arcsec=60.0, service=FakeService(rows))
    assert neighbours == []


def test_sources_too_faint_to_matter_are_dropped():
    rows = [src(POS["ra_deg"], POS["dec_deg"], 10.0, "target"),
            src(POS["ra_deg"] + 0.001, POS["dec_deg"], 25.0, "negligible")]
    _, neighbours = find_neighbours(**POS, mag_limit=8.0, service=FakeService(rows))
    assert neighbours == []


def test_neighbours_are_ordered_by_flux_not_distance():
    """A bright source further out matters more than a faint one nearby."""
    rows = [src(POS["ra_deg"], POS["dec_deg"], 10.0, "target"),
            src(POS["ra_deg"] + 0.0005, POS["dec_deg"], 17.0, "faint-close"),
            src(POS["ra_deg"] + 0.002, POS["dec_deg"], 11.0, "bright-far")]
    _, neighbours = find_neighbours(**POS, service=FakeService(rows))
    assert [n["source_id"] for n in neighbours] == ["bright-far", "faint-close"]


def test_unreachable_service_raises():
    with pytest.raises(CatalogUnavailable):
        find_neighbours(**POS, service=FakeService(error="timeout"))


# --- evidence -----------------------------------------------------------------

def signal(depth_ppm=None):
    return Signal(signal_id="X.01", source="test", depth_ppm=depth_ppm, **POS)


def test_clean_aperture_reports_full_dilution():
    rows = [src(POS["ra_deg"], POS["dec_deg"], 10.0, "target")]
    ev = crossmatch_neighbours(signal(), service=FakeService(rows))
    assert ev[0].payload["dilution"] == pytest.approx(1.0)
    assert ev[0].payload["neighbour_count"] == 0


def test_depth_correction_is_emitted_when_a_depth_is_known():
    rows = [src(POS["ra_deg"], POS["dec_deg"], 10.0, "target"),
            src(POS["ra_deg"] + 0.001, POS["dec_deg"], 10.0, "twin")]
    ev = crossmatch_neighbours(signal(depth_ppm=320), service=FakeService(rows))
    derived = [e for e in ev if e.kind is EvidenceKind.DERIVED]
    assert len(derived) == 1
    assert derived[0].payload["corrected_depth_ppm"] == pytest.approx(640, abs=1)


def test_no_depth_means_no_correction_claimed():
    """Without a measured depth there is nothing to correct, and inventing one
    would be an unsourced claim."""
    rows = [src(POS["ra_deg"], POS["dec_deg"], 10.0, "target"),
            src(POS["ra_deg"] + 0.001, POS["dec_deg"], 10.0, "twin")]
    ev = crossmatch_neighbours(signal(), service=FakeService(rows))
    assert not [e for e in ev if e.kind is EvidenceKind.DERIVED]


def test_faint_neighbour_is_reported_as_unable_to_explain():
    rows = [src(POS["ra_deg"], POS["dec_deg"], 10.0, "target"),
            src(POS["ra_deg"] + 0.001, POS["dec_deg"], 17.0, "faint")]
    ev = crossmatch_neighbours(signal(depth_ppm=10_000), service=FakeService(rows))
    verdicts = [e.payload.get("could_explain_signal") for e in ev
                if "could_explain_signal" in e.payload]
    assert verdicts == [False]


def test_bright_neighbour_is_reported_as_able_to_explain():
    rows = [src(POS["ra_deg"], POS["dec_deg"], 10.0, "target"),
            src(POS["ra_deg"] + 0.001, POS["dec_deg"], 10.5, "bright")]
    ev = crossmatch_neighbours(signal(depth_ppm=320), service=FakeService(rows))
    verdicts = [e.payload.get("could_explain_signal") for e in ev
                if "could_explain_signal" in e.payload]
    assert verdicts == [True]


def test_all_evidence_carries_a_source():
    rows = [src(POS["ra_deg"], POS["dec_deg"], 10.0, "target"),
            src(POS["ra_deg"] + 0.001, POS["dec_deg"], 12.0, "n1")]
    for e in crossmatch_neighbours(signal(depth_ppm=500), service=FakeService(rows)):
        assert e.source.strip()


def test_no_source_close_enough_means_no_target():
    """Gaia sees something almost everywhere, so proximity has to be required.

    Without this, a distant unrelated source is promoted to target and every
    quantity downstream is computed against the wrong star.
    """
    # Offset in declination, not right ascension: at dec -80 the meridians
    # converge, so 0.008 deg of RA is under 5 arcsec (D-018).
    rows = [src(POS["ra_deg"], POS["dec_deg"] + 0.005, 12.0, "far")]   # 18 arcsec
    target, neighbours = find_neighbours(**POS, service=FakeService(rows))
    assert target is None
    assert neighbours == []


def test_absent_target_is_reported_as_such():
    rows = [src(POS["ra_deg"], POS["dec_deg"] + 0.005, 12.0, "far")]   # 18 arcsec
    ev = crossmatch_neighbours(signal(depth_ppm=900), service=FakeService(rows))
    assert ev[0].payload["target_found"] is False
    assert "cannot be attributed to a star" in ev[0].summary


def test_a_brighter_neighbour_raises_a_misidentification_alert():
    """If something in the aperture outshines the target, the position probably
    resolved to the wrong star."""
    rows = [src(POS["ra_deg"], POS["dec_deg"], 14.0, "assumed-target"),
            src(POS["ra_deg"] + 0.002, POS["dec_deg"], 10.0, "much-brighter")]
    ev = crossmatch_neighbours(signal(depth_ppm=900), service=FakeService(rows))
    assert any(e.payload.get("target_identification_doubtful") for e in ev)


class RecordingService(FakeService):
    """Keeps the ADQL it was handed, so the query itself can be asserted on."""

    def __init__(self, rows=None):
        super().__init__(rows)
        self.adql = None

    def search(self, adql):
        self.adql = adql
        return super().search(adql)


def test_the_prefilter_is_a_cone_not_a_coordinate_box():
    """A box on plain ra/dec has a seam at RA 0; a cone has none, and it is the
    form Gaia's spatial index serves."""
    predicate = _cone_predicate(84.29928, -80.464604, 60.0)
    assert "CONTAINS" in predicate
    assert "CIRCLE('ICRS'" in predicate
    assert "BETWEEN" not in predicate


@pytest.mark.parametrize("ra_deg", [0.0, 0.004, 359.996, 360.0, 180.0])
def test_positions_on_the_ra_seam_still_select_their_own_centre(ra_deg):
    """The defect this replaces: an RA interval built by subtraction does not
    wrap, so near RA 0 the query read `BETWEEN -0.01 AND 0.01` and matched
    nothing. Every signal in that strip came back as 'no Gaia source here',
    which is indistinguishable from a real answer."""
    service = RecordingService([src(ra_deg, -80.46, 12.0, "centre")])
    find_neighbours(ra_deg=ra_deg, dec_deg=-80.46, service=service)
    assert repr(ra_deg) in service.adql
    assert "BETWEEN" not in service.adql


def test_the_cone_radius_is_the_aperture_converted_to_degrees():
    """ADQL geometry is in degrees; the aperture is quoted in arcseconds.
    Passing 60 where 60/3600 belongs would query a cone 3600 times too wide."""
    predicate = _cone_predicate(10.0, 20.0, 60.0)
    assert repr(60.0 / 3600.0) in predicate


def test_exact_separation_is_still_filtered_after_the_cone():
    """The cone is a prefilter, not the method. A source the archive returns
    outside the aperture is still dropped locally, so loosening or tightening
    the prefilter cannot change which neighbours are reported."""
    rows = [
        src(POS["ra_deg"], POS["dec_deg"], 12.0, "target"),
        src(POS["ra_deg"], POS["dec_deg"] + 0.03, 12.0, "108-arcsec-away"),
    ]
    target, neighbours = find_neighbours(**POS, service=FakeService(rows))
    assert target["source_id"] == "target"
    assert [n["source_id"] for n in neighbours] == []
