"""The MCP tools against the real archives. Marked network."""

import pytest

from astro_hunter.mcp import server as S

POS = (84.29928, -80.464604)


@pytest.mark.network
def test_pi_mensae_through_the_confirmed_planets_tool():
    result = S.check_confirmed_planets(*POS, period_days=6.268227)
    assert "error" not in result
    assert result["match_count"] >= 1
    assert any(p["period_relation"] == "match" for p in result["planets"])


@pytest.mark.network
def test_pi_mensae_through_the_aperture_tool():
    result = S.check_aperture_contamination(*POS, depth_ppm=321)
    assert "error" not in result
    assert result["target_found"] is True
    assert result["dilution"] > 0.9
    assert result["brighter_neighbours"] == 0


@pytest.mark.network
def test_a_position_with_no_close_star_is_reported_as_such():
    result = S.check_aperture_contamination(ra_deg=12.3456, dec_deg=-33.9876,
                                            depth_ppm=900)
    assert "error" not in result
    if result["target_found"] is False:
        assert "neighbours" not in result
