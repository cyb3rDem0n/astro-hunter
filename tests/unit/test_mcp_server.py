"""The MCP surface: schemas, small results, errors as data, no verdict leak."""

import asyncio

from astro_hunter.domains.exoplanets import catalogs, neighbours
from astro_hunter.domains.exoplanets.photometry import tess
from astro_hunter.mcp import server as S

POS = (84.29928, -80.464604)


def tools():
    return {t.name: t for t in asyncio.run(S.mcp.list_tools())}


def test_the_expected_tools_are_registered():
    assert set(tools()) == {
        "check_confirmed_planets",
        "check_aperture_contamination",
        "check_period_relation",
        "check_instrumental_coincidence",
        "check_odd_even_depth",
    }


def test_every_tool_documents_itself():
    for name, t in tools().items():
        assert t.description and len(t.description) > 120, name


def test_positions_are_required_and_periods_are_not():
    schema = tools()["check_confirmed_planets"].parameters
    assert set(schema["required"]) == {"ra_deg", "dec_deg"}


def test_no_tool_exposes_a_verdict():
    for name, t in tools().items():
        assert "verdict" not in (t.description or "").lower(), name
        assert "verdict" not in str(t.parameters).lower(), name


def test_an_unreachable_archive_returns_an_error_not_an_exception(monkeypatch):
    def down(*a, **k):
        raise catalogs.CatalogUnavailable("connection refused")

    monkeypatch.setattr(catalogs, "find_confirmed_planets", down)
    result = S.check_confirmed_planets(*POS)
    assert "error" in result
    assert "not evidence of absence" in result["hint"]


def test_an_unreachable_gaia_says_it_is_not_a_clean_aperture(monkeypatch):
    def down(*a, **k):
        raise neighbours.CatalogUnavailable("timeout")

    monkeypatch.setattr(neighbours, "crossmatch_neighbours", down)
    result = S.check_aperture_contamination(*POS, depth_ppm=321)
    assert "error" in result
    assert "not evidence of a clean aperture" in result["hint"]


def test_results_are_capped(monkeypatch):
    many = [
        {"planet": f"P{i} b", "host": f"P{i}", "separation_arcsec": 0.1 * i,
         "period_days": 3.0, "radius_earth": 2.0, "discovery_year": 2020,
         "discovery_facility": "TESS"}
        for i in range(50)
    ]
    monkeypatch.setattr(catalogs, "find_confirmed_planets", lambda *a, **k: many)
    result = S.check_confirmed_planets(*POS)
    assert result["match_count"] == 50
    assert len(result["planets"]) == S.MAX_ITEMS


def test_period_relation_recognises_the_classic_double():
    assert S.check_period_relation(12.5356, 6.2678139)["relation"] == "harmonic:2"


def test_period_relation_survives_a_zero_denominator():
    assert S.check_period_relation(6.27, 0.0)["relation"] == "unknown"


def test_period_relation_is_reported_per_planet(monkeypatch):
    monkeypatch.setattr(catalogs, "find_confirmed_planets", lambda *a, **k: [
        {"planet": "pi Men c", "host": "pi Men", "separation_arcsec": 0.0,
         "period_days": 6.2678139, "radius_earth": 2.0,
         "discovery_year": 2018, "discovery_facility": "TESS"},
        {"planet": "pi Men b", "host": "pi Men", "separation_arcsec": 0.0,
         "period_days": 2093.07, "radius_earth": None,
         "discovery_year": 2001, "discovery_facility": "AAT"},
    ])
    result = S.check_confirmed_planets(*POS, period_days=6.268227)
    relations = {p["planet"]: p["period_relation"] for p in result["planets"]}
    assert relations["pi Men c"] == "match"
    assert relations["pi Men b"] == "unrelated"


def test_an_absent_target_is_stated_plainly(monkeypatch):
    from datetime import UTC, datetime

    from astro_hunter.core.models import Evidence, EvidenceKind

    monkeypatch.setattr(neighbours, "crossmatch_neighbours", lambda *a, **k: [
        Evidence(kind=EvidenceKind.NEIGHBOUR, source="Gaia DR3",
                 summary="no Gaia source within 10.5 arcsec of the position",
                 retrieved_at=datetime.now(UTC),
                 payload={"target_found": False})
    ])
    result = S.check_aperture_contamination(*POS, depth_ppm=900)
    assert result["target_found"] is False
    assert "neighbours" not in result


# --- check_instrumental_coincidence (D-041) ------------------------------------

def test_an_unassessable_target_says_so_not_clean(monkeypatch):
    """No 2-minute product (or no target_id) must read as 'not assessed', never
    as 'nothing wrong' - the same doctrine every other unreachable check gets."""
    from datetime import UTC, datetime

    from astro_hunter.core.models import Evidence, EvidenceKind

    monkeypatch.setattr(tess, "check_instrumental_coincidence", lambda *a, **k: [
        Evidence(kind=EvidenceKind.INSTRUMENTAL_WINDOW, source="observing record",
                 summary="no SPOC 2-minute product for TIC 1; instrumental "
                         "coincidence not assessable",
                 retrieved_at=datetime.now(UTC),
                 payload={"assessed": False, "available_2min": False})
    ])
    result = S.check_instrumental_coincidence(
        target_id="TIC 1", epoch_btjd=1.5, period_days=6.27,
    )
    assert result == {
        "assessed": False,
        "finding": "no SPOC 2-minute product for TIC 1; instrumental "
                   "coincidence not assessable",
    }


def test_an_assessed_result_is_flattened_to_a_small_dict(monkeypatch):
    from datetime import UTC, datetime

    from astro_hunter.core.models import Evidence, EvidenceKind

    monkeypatch.setattr(tess, "check_instrumental_coincidence", lambda *a, **k: [
        Evidence(kind=EvidenceKind.INSTRUMENTAL_WINDOW, source="observing record",
                 summary="6 of 6 predicted transits have data coverage above 50%",
                 retrieved_at=datetime.now(UTC),
                 payload={"assessed": True, "predicted_transits": 6,
                          "observed_transits": 6, "baseline_days": 27.4,
                          "cadence_days": 120 / 86400,
                          "quality_flags_available": True, "per_transit": []})
    ])
    result = S.check_instrumental_coincidence(
        target_id="TIC 1", epoch_btjd=1.5, period_days=6.27, duration_hours=2.8,
    )
    assert result["assessed"] is True
    assert result["predicted_transits"] == 6
    assert result["observed_transits"] == 6
    assert result["quality_flags_available"] is True
    assert "per_transit" not in result
    assert len(result["findings"]) == 1


# --- check_odd_even_depth (D-038) -----------------------------------------------

def test_odd_even_unassessable_target_says_so_not_clean(monkeypatch):
    """Same doctrine as check_instrumental_coincidence: unreachable is not
    clean."""
    from datetime import UTC, datetime

    from astro_hunter.core.models import Evidence, EvidenceKind

    monkeypatch.setattr(tess, "check_odd_even_depth", lambda *a, **k: [
        Evidence(kind=EvidenceKind.DERIVED, source="light curve (odd/even depth)",
                 summary="no SPOC 2-minute product for TIC 1; odd/even depth "
                         "not assessable",
                 retrieved_at=datetime.now(UTC),
                 payload={"assessed": False, "available_2min": False})
    ])
    result = S.check_odd_even_depth(
        target_id="TIC 1", epoch_btjd=1.5, period_days=6.27, duration_hours=2.8,
    )
    assert result == {
        "assessed": False,
        "finding": "no SPOC 2-minute product for TIC 1; odd/even depth "
                   "not assessable",
    }


def test_odd_even_assessed_result_is_flattened_to_a_small_dict(monkeypatch):
    from datetime import UTC, datetime

    from astro_hunter.core.models import Evidence, EvidenceKind

    monkeypatch.setattr(tess, "check_odd_even_depth", lambda *a, **k: [
        Evidence(kind=EvidenceKind.DERIVED, source="light curve (odd/even depth)",
                 summary="odd-transit depth 20000 ppm vs even-transit depth "
                         "10000 ppm (5 vs 5 transits): 8.4-sigma, consistent "
                         "with an eclipsing binary at twice the search period",
                 retrieved_at=datetime.now(UTC),
                 payload={"assessed": True, "odd_depth_ppm": 20000.0,
                          "even_depth_ppm": 10000.0, "odd_transits": 5,
                          "even_transits": 5, "odd_even_sigma": 8.4,
                          "odd_even_significant": True})
    ])
    result = S.check_odd_even_depth(
        target_id="TIC 1", epoch_btjd=1.5, period_days=6.27, duration_hours=2.8,
    )
    assert result["assessed"] is True
    assert result["significant"] is True
    assert result["odd_depth_ppm"] == 20000.0
    assert result["even_depth_ppm"] == 10000.0
    assert result["sigma"] == 8.4
    assert len(result["findings"]) == 1
