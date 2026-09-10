"""Candidate queue - ordering and persistence.

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``.

Responsibility: hold signals awaiting triage, expose them in priority order,
and record what has been processed so a run can resume rather than restart.

Boundaries: knows nothing about why a signal is interesting. Ordering is
supplied by the domain and by the active-learning layer, not decided here.
"""
