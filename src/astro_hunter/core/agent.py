"""The agent loop: a language model reasoning over the triage tools.

What an agent is, mechanically: a loop. The model is sent the signal and the
list of tools it may call. It replies either with a tool call — which this code
executes, returning the result — or with a final answer. The conversation grows
with each turn, because the API keeps no state between calls, and the whole
history is re-sent every time.

That last point is why the guardrails below are not optional. Cost grows with
the square of the turn count, not linearly, and a model that loops will spend
real money doing it.

**Three guardrails.**

*Iteration ceiling.* A model that cannot decide will keep calling tools. The
loop stops and reports that it stopped, which is a result, not a failure.

*Token budget.* Checked after every call against the running total. Stops
before the next request rather than after discovering the overrun.

*Result truncation.* A tool returning an unexpectedly large payload would be
paid for in full. Capped at the boundary.

**The output contract.** The model submits its verdict through a tool rather
than in prose, so the result is structured by construction instead of parsed
out of free text. Every claim must cite the tool that produced it (D-014).

Note that `submit_verdict` is the agent's *output channel*, not an evidence
source. D-023 forbids exposing the rule engine's verdict to the agent; it does
not forbid the agent from stating its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

VERDICT_VALUES = [
    "known", "instrumental", "contaminated", "explained",
    "interesting", "insufficient",
]

SUBMIT_VERDICT_TOOL = {
    "name": "submit_verdict",
    "description": (
        "Submit your final assessment. Call this once, when you have gathered "
        "enough evidence or established that you cannot. Do not call it before "
        "using the evidence tools."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": VERDICT_VALUES,
                "description": (
                    "known: already catalogued or published. "
                    "instrumental: consistent with a spacecraft artefact. "
                    "contaminated: plausibly from a neighbouring source. "
                    "explained: real, on the target, but not a planet. "
                    "interesting: survives every check, unresolved. "
                    "insufficient: not enough evidence to place it."
                ),
            },
            "confidence": {
                "type": "number",
                "description": "0 to 1. Your own summary of how decisive the "
                               "evidence is. Not a probability.",
            },
            "reasoning": {
                "type": "string",
                "description": (
                    "Two or three sentences. Every factual claim must state "
                    "which tool produced it. If you did not retrieve a fact "
                    "from a tool, do not assert it."
                ),
            },
            "evidence_used": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names of the tools whose results you relied on.",
            },
        },
        "required": ["verdict", "confidence", "reasoning"],
    },
}

SYSTEM_PROMPT = """You triage candidate astronomical signals.

For each signal you decide whether it is already known, explained by the
instrument, plausibly caused by a neighbouring star, or worth an astronomer's
time.

Method:
1. Check the confirmed-planet catalogue first. Most candidates are already
   known and this costs one query.
2. If a planet is catalogued at the position, compare periods. A match or a
   harmonic means the same planet. An UNRELATED period means the star is known
   but this signal is not accounted for - that is a candidate additional
   planet, which is more interesting, not less.
3. Check the aperture for contaminating sources when a depth is available.
4. Submit a verdict.

Hard constraints:
- Never state a number you did not receive from a tool. No periods, depths,
  separations or probabilities from your own knowledge.
- Never treat a tool error as a negative result. "The archive is unreachable"
  is not "nothing is catalogued there". If a check could not run, the verdict
  is insufficient.
- If no star is found close enough to the position, nothing downstream can be
  assessed and the verdict is insufficient.
- Cite the tool behind every factual claim in your reasoning.

Be economical: do not call a tool whose answer you already have."""


@dataclass
class AgentRun:
    """What happened, in enough detail to compare against the rule baseline."""

    signal_id: str
    verdict: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    evidence_used: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "completed"
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def cost_usd(self, input_per_mtok: float, output_per_mtok: float) -> float:
        return (self.input_tokens / 1e6 * input_per_mtok
                + self.output_tokens / 1e6 * output_per_mtok)


def anthropic_tool_schemas(mcp_tools) -> list[dict]:
    """Translate fastmcp tool definitions into the API's tool format.

    fastmcp exposes the JSON schema as ``parameters``; the Anthropic API calls
    the same thing ``input_schema``. Deriving them from the server rather than
    writing them twice means a change to a tool signature cannot silently
    diverge from what the model is told.
    """
    return [
        {"name": t.name, "description": t.description, "input_schema": t.parameters}
        for t in mcp_tools
    ]


def describe_signal(signal) -> str:
    parts = [f"Signal {signal.signal_id}",
             f"position: RA {signal.ra_deg}, Dec {signal.dec_deg} (ICRS, degrees)"]
    if signal.period_days:
        parts.append(f"period: {signal.period_days} days")
    if signal.depth_ppm:
        parts.append(f"transit depth: {signal.depth_ppm} ppm")
    if signal.duration_hours:
        parts.append(f"transit duration: {signal.duration_hours} hours")
    if signal.target_id:
        parts.append(f"target: {signal.target_id}")
    return "\n".join(parts)


def run_agent(
    signal,
    client,
    tool_schemas: list[dict],
    execute_tool,
    model: str = "claude-sonnet-5",
    max_iterations: int = 8,
    token_budget: int = 60_000,
    max_result_chars: int = 6_000,
) -> AgentRun:
    """Reason over one signal and return the agent's assessment.

    ``execute_tool(name, arguments) -> dict`` runs a tool and returns its
    result. Errors are expected to come back as data, not exceptions (D-024).
    """
    run = AgentRun(signal_id=signal.signal_id, started_at=datetime.now(UTC))
    tools = [*tool_schemas, SUBMIT_VERDICT_TOOL]
    messages = [{"role": "user", "content": describe_signal(signal)}]

    for i in range(max_iterations):
        run.iterations = i + 1

        try:
            response = client.messages.create(
                model=model,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001 - an API failure is a run outcome
            run.stop_reason = "api_error"
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished_at = datetime.now(UTC)
            return run

        run.input_tokens += response.usage.input_tokens
        run.output_tokens += response.usage.output_tokens

        messages.append({"role": "assistant", "content": response.content})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            run.stop_reason = "no_verdict_submitted"
            run.finished_at = datetime.now(UTC)
            return run

        results = []
        for block in tool_uses:
            run.tools_called.append(block.name)

            if block.name == "submit_verdict":
                run.verdict = block.input.get("verdict")
                run.confidence = block.input.get("confidence")
                run.reasoning = block.input.get("reasoning")
                run.evidence_used = block.input.get("evidence_used", [])
                run.finished_at = datetime.now(UTC)
                return run

            try:
                output = execute_tool(block.name, block.input)
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                output = {"error": f"{type(exc).__name__}: {exc}"}

            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(output, default=str)[:max_result_chars],
            })

        messages.append({"role": "user", "content": results})

        if run.input_tokens + run.output_tokens > token_budget:
            run.stop_reason = "token_budget_exceeded"
            run.finished_at = datetime.now(UTC)
            return run

    run.stop_reason = "max_iterations"
    run.finished_at = datetime.now(UTC)
    return run
