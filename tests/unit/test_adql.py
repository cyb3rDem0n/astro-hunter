"""The shared spatial prefilter. Pure string building; no network, no service."""

import pytest

from astro_hunter.core.adql import cone_predicate


def test_the_prefilter_is_a_cone_not_a_coordinate_box():
    """A box on plain ra/dec has a seam at RA 0; a cone has none, and it is the
    form the archives' spatial indexes serve."""
    predicate = cone_predicate(84.29928, -80.464604, 60.0)
    assert "CONTAINS" in predicate
    assert "CIRCLE('ICRS'" in predicate
    assert "BETWEEN" not in predicate


def test_the_radius_is_converted_from_arcseconds_to_degrees():
    """ADQL geometry is in degrees; apertures and match radii are quoted in
    arcseconds throughout this codebase. Passing 60 where 60/3600 belongs would
    query a cone 3600 times too wide."""
    assert repr(60.0 / 3600.0) in cone_predicate(10.0, 20.0, 60.0)


@pytest.mark.parametrize("ra_deg", [0.0, 0.004, 180.0, 359.996, 360.0])
def test_the_centre_survives_the_seam(ra_deg):
    """The defect this replaces built the RA interval by subtraction, which does
    not wrap; near RA 0 the centre was lost entirely."""
    predicate = cone_predicate(ra_deg, -80.46, 60.0)
    assert repr(ra_deg) in predicate
