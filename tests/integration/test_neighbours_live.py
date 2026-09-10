"""Live Gaia DR3 checks. Marked network; excluded from the default run."""

import pytest

from astro_hunter.core.models import Signal
from astro_hunter.domains.exoplanets.neighbours import (
    crossmatch_neighbours,
    find_neighbours,
)

PI_MEN = {"ra_deg": 84.29928, "dec_deg": -80.464604}


@pytest.mark.network
def test_target_is_found_and_is_the_brightest_thing_around():
    target, neighbours = find_neighbours(**PI_MEN, radius_arcsec=60.0)
    assert target is not None, "pi Mensae is naked-eye bright; Gaia must see it"
    for n in neighbours:
        assert n["g_mag"] > target["g_mag"], (
            "a source brighter than the target within the aperture would mean "
            "the position resolved to the wrong star"
        )


@pytest.mark.network
def test_aperture_is_largely_uncontaminated():
    """Pi Mensae is bright and isolated, so dilution should be close to 1.

    If this ever fails, either the magnitude handling is wrong or the position
    is resolving to a different star. Both are worth stopping for.
    """
    sig = Signal(signal_id="pi-men", source="catalogue", depth_ppm=321.0, **PI_MEN)
    ev = crossmatch_neighbours(sig, radius_arcsec=60.0)
    summary = ev[0]
    assert summary.payload["dilution"] > 0.9


@pytest.mark.network
def test_empty_field_returns_no_target_without_raising():
    _target, neighbours = find_neighbours(ra_deg=12.3456, dec_deg=-33.9876,
                                          radius_arcsec=2.0)
    assert neighbours == []
