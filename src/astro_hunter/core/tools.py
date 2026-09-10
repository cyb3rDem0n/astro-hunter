"""Tool registry - what the agent is allowed to call.

NOT IMPLEMENTED. Placeholder; see ``docs/ARCHITECTURE.md``.

Responsibility: expose domain checks as callable tools with schemas, and
enforce that every tool result carries its provenance.

Boundaries: tool results must be small. A result is paid for in context tokens
and read by a model with no memory of the last call, so returning thousands of
catalog rows is both expensive and useless. Truncate, limit, aggregate.

Errors are data, not exceptions: a tool that raises kills the loop, so failures
return a structured error the agent can react to.
"""
