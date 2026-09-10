"""Cross-match logic. No network: these exercise pure functions and a fake service."""

from datetime import UTC, datetime

import pytest

from astro_hunter.core.models import EvidenceKind, Signal
from astro_hunter.domains.exoplanets.catalogs import (
    CatalogUnavailable,
    crossmatch_confirmed,
    find_confirmed_planets,
    period_relation,
)

PI_MEN = {"ra_deg": 84.29928, "dec_deg": -80.464604}
PI_MEN_C_PERIOD = 6.2678139


class FakeService:
    """Stands in for the TAP service. Returns rows, or raises."""

    def __init__(self, rows=None, error=None):
        self._rows, self._error = rows or [], error

    def search(self, adql):
        if self._error:
            raise RuntimeError(self._error)
        return self

    def to_table(self):
        return self._rows


def row(ra, dec, name="Test b", host="Test", period=3.0, rade=2.0, year=2020, fac="TESS"):
    return {"ra": ra, "dec": dec, "pl_name": name, "hostname": host,
            "pl_orbper": period, "pl_rade": rade, "disc_year": year, "disc_facility": fac}


# --- period_relation ----------------------------------------------------------

@pytest.mark.parametrize("candidate,known,expected", [
    (6.2678139, 6.2678139, "match"),
    (6.268227, 6.2678139, "match"),          # our own detection, within tolerance
    (12.5356, 6.2678139, "harmonic:2"),      # the classic BLS double
    (3.1339, 6.2678139, "harmonic:0.5"),     # and the classic half
    (18.803, 6.2678139, "harmonic:3"),
    (4.1, 6.2678139, "unrelated"),
    (None, 6.2678139, "unknown"),
    (6.27, None, "unknown"),
    (6.27, 0.0, "unknown"),
])
def test_period_relation(candidate, known, expected):
    assert period_relation(candidate, known) == expected


def test_our_pi_mensae_detection_matches_the_catalogue():
    """The pipeline found 6.268227; the catalogue says 6.2678139 (D-007)."""
    assert period_relation(6.268227, PI_MEN_C_PERIOD) == "match"


# --- positional filtering -----------------------------------------------------

def test_far_source_inside_the_box_is_rejected_by_exact_separation():
    """The ADQL box over-selects on purpose; astropy does the real cut."""
    far = row(PI_MEN["ra_deg"] + 0.05, PI_MEN["dec_deg"])   # ~30 arcsec at this dec
    found = find_confirmed_planets(**PI_MEN, radius_arcsec=5.0,
                                   service=FakeService([far]))
    assert found == []


def test_close_source_is_kept_with_its_separation():
    close = row(PI_MEN["ra_deg"], PI_MEN["dec_deg"] + 0.0005)   # 1.8 arcsec
    found = find_confirmed_planets(**PI_MEN, radius_arcsec=5.0,
                                   service=FakeService([close]))
    assert len(found) == 1
    assert found[0]["separation_arcsec"] == pytest.approx(1.8, abs=0.2)


def test_matches_are_sorted_by_separation():
    rows = [row(PI_MEN["ra_deg"], PI_MEN["dec_deg"] + 0.0008, name="Far b"),
            row(PI_MEN["ra_deg"], PI_MEN["dec_deg"] + 0.0002, name="Near b")]
    found = find_confirmed_planets(**PI_MEN, service=FakeService(rows))
    assert [p["planet"] for p in found] == ["Near b", "Far b"]


def test_unreachable_service_raises_instead_of_returning_empty():
    """An outage must not be readable as 'nothing known here'."""
    with pytest.raises(CatalogUnavailable):
        find_confirmed_planets(**PI_MEN, service=FakeService(error="connection refused"))


# --- evidence -----------------------------------------------------------------

def signal(period=None):
    return Signal(signal_id="X.01", source="test", period_days=period, **PI_MEN)


def test_no_match_still_produces_evidence():
    """Absence is a finding, and it needs a source like any other."""
    ev = crossmatch_confirmed(signal(), service=FakeService([]))
    assert len(ev) == 1
    assert ev[0].kind is EvidenceKind.CATALOG_MATCH
    assert "no confirmed planet" in ev[0].summary
    assert ev[0].source


def test_match_with_same_period_reports_match():
    close = row(PI_MEN["ra_deg"], PI_MEN["dec_deg"], name="pi Men c",
                period=PI_MEN_C_PERIOD)
    ev = crossmatch_confirmed(signal(period=6.268227), service=FakeService([close]))
    assert ev[0].identifier == "pi Men c"
    assert ev[0].payload["period_relation"] == "match"


def test_known_star_with_unrelated_period_stays_distinguishable():
    """Positional coincidence is not identity.

    A known host with a signal at an unrelated period is a candidate additional
    planet, not a rediscovery. If this ever collapses to a bare 'known', the
    system stops being able to find planets in known systems.
    """
    close = row(PI_MEN["ra_deg"], PI_MEN["dec_deg"], name="pi Men c",
                period=PI_MEN_C_PERIOD)
    ev = crossmatch_confirmed(signal(period=1.7), service=FakeService([close]))
    assert ev[0].payload["period_relation"] == "unrelated"


def test_evidence_carries_provenance():
    close = row(PI_MEN["ra_deg"], PI_MEN["dec_deg"])
    ev = crossmatch_confirmed(signal(), service=FakeService([close]))[0]
    assert ev.source and ev.retrieved_at <= datetime.now(UTC)
    assert ev.separation_arcsec is not None
