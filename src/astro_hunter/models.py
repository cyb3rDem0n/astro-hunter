"""Models - typed data structures exchanged between layers.

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``.

Responsibility
--------------
The objects that cross layer boundaries: a retrieved product, a preprocessed
time series, a candidate, a characterized candidate, a validation report.

Boundaries
----------
Contains no scientific mathematics. Structures only.

Units are part of the contract. A bare float named ``duration`` is a defect:
either the type carries the unit (``astropy.units.Quantity``) or the field name
does (``duration_days``). Inconsistent conventions between layers are how a
factor of 24 reaches a published number.
"""
