"""Characterization - measuring properties of a detected candidate.

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``.

Responsibility
--------------
Measure period, transit duration, depth, noise, approximate SNR and number of
observed events for a candidate produced by ``detection``.

Boundaries
----------
Consumes a candidate; does not produce one. Does not establish planetary nature
- that judgement belongs to no module in this package.

Every returned quantity carries its unit, through its type or through an
unambiguous field name. Approximate quantities say so: an SNR estimated from a
simple noise model is not the same object as a fitted one.
"""
