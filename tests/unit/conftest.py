"""Shared fakes for the unit tests."""

import re

import astropy.units as u
import pytest
from astropy.coordinates import SkyCoord

CIRCLE = re.compile(
    r"CIRCLE\(\s*'ICRS'\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)"
)
RANGE = re.compile(r"\b(ra|dec)\s+BETWEEN\s+([-+0-9.eE]+)\s+AND\s+([-+0-9.eE]+)")


class SpatialFakeService:
    """A fake TAP service that actually applies the query's spatial predicate.

    The plain `FakeService` in these modules hands back its rows whatever the
    query says. That is convenient for testing what happens to rows once they
    arrive, and it is exactly why a prefilter that could not match anything went
    unnoticed: every test passed while the real archive returned nothing.

    This one reads the predicate and filters on it, so a query with a seam in it
    fails here the way it failed against the archive. It understands both forms
    — the cone and the coordinate box it replaced — so the box does not quietly
    start passing again.
    """

    def __init__(self, rows=None, error=None):
        self._rows, self._error = rows or [], error
        self._selected = []
        self.adql = None

    def search(self, adql):
        self.adql = adql
        if self._error:
            raise RuntimeError(self._error)
        self._selected = [r for r in self._rows if self._matches(adql, r)]
        return self

    def to_table(self):
        return self._selected

    def _matches(self, adql: str, row) -> bool:
        circle = CIRCLE.search(adql)
        if circle:
            ra0, dec0, radius_deg = (float(g) for g in circle.groups())
            centre = SkyCoord(ra=ra0 * u.deg, dec=dec0 * u.deg, frame="icrs")
            here = SkyCoord(ra=row["ra"] * u.deg, dec=row["dec"] * u.deg, frame="icrs")
            return float(centre.separation(here).deg) <= radius_deg

        ranges = {
            m.group(1): (float(m.group(2)), float(m.group(3))) for m in RANGE.finditer(adql)
        }
        if ranges:
            # Deliberately literal: this is what the archive does with a range,
            # including failing to wrap at RA 360.
            return all(lo <= row[col] <= hi for col, (lo, hi) in ranges.items())

        raise AssertionError(f"no spatial predicate found in query: {adql}")


@pytest.fixture
def spatial_service():
    """Factory for a fake TAP service that honours the query's spatial predicate."""
    return SpatialFakeService
