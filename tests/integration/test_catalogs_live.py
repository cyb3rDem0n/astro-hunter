"""Live archive checks. Marked network; excluded from the default run."""

import pytest

from astro_hunter.core.models import Signal
from astro_hunter.domains.exoplanets.catalogs import (
    crossmatch_confirmed,
    find_confirmed_planets,
)

PI_MEN = {"ra_deg": 84.29928, "dec_deg": -80.464604}


@pytest.mark.network
def test_pi_mensae_is_found_in_the_confirmed_catalogue():
    found = find_confirmed_planets(**PI_MEN, radius_arcsec=5.0)
    assert found, "pi Mensae hosts confirmed planets; an empty result is a bug"
    assert any("men" in p["planet"].lower() for p in found)


@pytest.mark.network
def test_empty_sky_returns_no_match():
    """A position with nothing catalogued must come back empty, not error."""
    found = find_confirmed_planets(ra_deg=12.3456, dec_deg=-33.9876, radius_arcsec=5.0)
    assert found == []


@pytest.mark.network
def test_our_detection_matches_the_catalogue_period():
    """End to end: 6.268227 from the pipeline against the archive (D-007)."""
    sig = Signal(signal_id="pi-men", source="local-pipeline",
                 period_days=6.268227, **PI_MEN)
    ev = crossmatch_confirmed(sig)
    relations = [e.payload.get("period_relation") for e in ev]
    assert "match" in relations, f"expected a period match, got {relations}"
