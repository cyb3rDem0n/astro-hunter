"""Pipeline - orchestration across layers.

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``.

Responsibility
--------------
Run a configured target through acquisition, preprocessing, detection,
characterization and validation, recording what was run with which parameters.

Boundaries
----------
Contains little or no scientific mathematics. Numerical methodology belongs to
the domain module so that it stays independently testable - an algorithm that
can only be exercised through the orchestrator is an algorithm without tests.

Reproducibility
---------------
Every artifact is reproducible from raw data plus code plus configuration. Run
parameters are recorded with the results, and results are never written back
into ``config/``.
"""
