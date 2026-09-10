"""Preprocessing - preparing a time series for scientific analysis.

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``. Preprocessing is
currently split between ``tess.py`` and ``scripts/02_detect_transit.py``, and
the two disagree - that discrepancy is D-004.

Responsibility
--------------
Missing-value handling, normalization, detrending, and conservative outlier
handling. Each transformation exposes its parameters and preserves temporal
coordinates.

Boundaries
----------
Must not search for signals. Data cleaning must be conservative: points are
never removed for making a candidate less convenient.

Blocked on
----------
D-004 - outlier rejection threshold and ordering. The two existing code paths
use different sigma values and clip at different points in the chain.

D-009 - symmetric vs asymmetric clipping. A transit is a decrease in flux, so
symmetric clipping can remove the signal being searched for, silently.

Both are open scientific decisions. Do not resolve them by adopting whichever
existing path is more convenient to import.
"""
