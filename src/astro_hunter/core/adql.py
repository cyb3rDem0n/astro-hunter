"""ADQL fragments shared by the catalog modules.

Only the spatial prefilter lives here so far. It is one function in `core/`
rather than a copy in each catalog module because the defect it replaces (D-034)
was duplicated: the same RA-wrap error existed independently in `catalogs.py`
and `neighbours.py`, and fixing one left the other wrong.
"""

from __future__ import annotations


def cone_predicate(ra_deg: float, dec_deg: float, radius_arcsec: float) -> str:
    """An ADQL cone around a position, for use as a prefilter.

    Returns a predicate over the table's ``ra``/``dec`` columns, in degrees, as
    ADQL geometry requires.

    This replaces a bounding box on plain ``ra``/``dec`` ranges (D-034). The box
    had a defect that produced no error: an RA interval built by subtraction does
    not wrap, so a query centred near RA 0 read like ``ra BETWEEN -0.001 AND
    0.002`` and could not match a source just below 360 degrees, however close it
    actually was. A cone has no seam to get wrong.

    It remains a prefilter, not the method. Callers still compute the exact
    angular separation with astropy afterwards and drop what falls outside the
    radius, so widening or narrowing this cannot change which sources are
    reported — only how many rows are fetched to find them. That is also where
    the convergence of RA towards the poles is handled (D-018).
    """
    return (
        f"1 = CONTAINS("
        f"POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {ra_deg!r}, {dec_deg!r}, {radius_arcsec / 3600.0!r}))"
    )
