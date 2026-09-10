"""TOI catalog as a queue source.

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``.

Responsibility: pull candidates from the TOI catalog and yield ``Signal``
objects.

Two modes, deliberately separate:

- **benchmark** - dispositions are retained as hidden labels for evaluation
  (D-013). The agent must not see them.
- **triage** - dispositions are not fetched at all.

Keeping these apart in code, rather than by discipline, is what stops a label
leaking into the input and quietly inflating every metric.
"""
