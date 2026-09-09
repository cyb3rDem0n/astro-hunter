"""Acquisition - locating and retrieving astronomical products.

NOT IMPLEMENTED. This module is a placeholder for the layer described in
``docs/ARCHITECTURE.md``. Acquisition currently lives in ``tess.py``.

Responsibility
--------------
Locate and retrieve observational products from remote archives. Inputs may
include TIC identifier, sector, mission, author, cadence, or other product
constraints.

Boundaries
----------
Must not classify or validate astrophysical signals. Must not apply scientific
transformations - those belong to ``preprocessing``.

Migration
---------
The download logic in ``tess.py`` moves here. The parameters it currently
hardcodes are recorded as D-001 and D-003 in ``docs/decisions.md`` and must not
change during the move: the refactor is required to be numerically neutral.
"""
