"""Detection - blind signal search.

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``. Detection currently
lives inline in ``scripts/02_detect_transit.py``, which also duplicates the
download instead of importing the package.

Responsibility
--------------
Blind periodic-signal search. For the current transit workflow: Box Least
Squares period search and the periodogram-derived quantities that follow.

Boundaries
----------
Must not use known catalog periods as priors to reproduce an expected answer
(blind detection). Must not import validation logic - the dependency direction
is acquisition -> preprocessing -> detection -> characterization -> validation.

Search grid parameters are D-006. They become arguments, not module constants,
before any multi-target run.

Blocked on
----------
D-004 and D-009, which determine the preprocessing this module receives.
"""
