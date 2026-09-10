"""Catalog cross-match for the exoplanet domain.

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``.

Planned sources: TOI catalog, NASA Exoplanet Archive confirmed planets, SIMBAD,
Gaia DR3, and a variable-star catalog. Each returns ``Evidence`` carrying the
matched identifier and angular separation, never a bare boolean.

This is the cheapest and most discriminating check in the whole system: most
candidates are already known, and finding that out costs one query. It runs
first for that reason.

"Poorly classified" is only measurable against what is classified. This module
is what makes novelty detectable, not a detour away from it.
"""
