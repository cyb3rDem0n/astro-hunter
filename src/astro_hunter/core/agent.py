"""Agent loop - orchestration over deterministic tools.

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``.

Responsibility: decide which tool to call next, when enough has been gathered,
and produce a verdict with a confidence and a written rationale.

Boundaries (D-014). The agent never produces a scientific number. Periods,
depths, separations and probabilities come from tools. Every claim in the
output traces to an ``Evidence`` record; unsourced statements are rejected at
the schema level rather than discouraged in a prompt.

Guardrails: iteration ceiling, token budget, truncation of tool output. An
agent without these will loop and spend real money overnight.
"""
