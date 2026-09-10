"""Evaluation against expert dispositions (D-013).

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``.

Responsibility: compare agent verdicts against labels assigned by human
experts, and report precision, recall and a confusion matrix per verdict class.

Also: precision@k over the queue - of the first k items surfaced, how many
proved worth a human's time. That is the metric the triage claim rests on.

Boundaries: reports numbers, never adjusts thresholds to improve them.
"""
