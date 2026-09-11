"""The agent loop, exercised against a scripted client. No API calls, no cost."""

from types import SimpleNamespace

import pytest

from astro_hunter.core.agent import (
    SUBMIT_VERDICT_TOOL,
    VERDICT_VALUES,
    AgentRun,
    anthropic_tool_schemas,
    describe_signal,
    run_agent,
)
from astro_hunter.core.models import Signal

POS = {"ra_deg": 84.29928, "dec_deg": -80.464604}


def sig(**kw):
    return Signal(signal_id="TOI-144.01", source="test", **POS, **kw)


def block_tool(name, inp, uid="t1"):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=uid)


def block_text(text):
    return SimpleNamespace(type="text", text=text)


class ScriptedClient:
    """Replays a fixed list of responses, recording what it was sent."""

    def __init__(self, responses, in_tokens=1000, out_tokens=100):
        self._responses = list(responses)
        self._in, self._out = in_tokens, out_tokens
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        # Snapshot: the loop mutates the same list object across turns, so
        # storing the reference would record only the final state.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        if not self._responses:
            raise AssertionError("the loop asked for more turns than were scripted")
        content = self._responses.pop(0)
        return SimpleNamespace(
            content=content,
            usage=SimpleNamespace(input_tokens=self._in, output_tokens=self._out),
        )


class FailingClient:
    def __init__(self, exc):
        self._exc = exc
        self.messages = self

    def create(self, **kwargs):
        raise self._exc


def verdict_block(verdict="interesting", confidence=0.6, reasoning="because",
                  evidence=None):
    return block_tool("submit_verdict", {
        "verdict": verdict, "confidence": confidence, "reasoning": reasoning,
        "evidence_used": evidence or ["check_confirmed_planets"],
    })


def noop_tool(name, args):
    return {"ok": True}


# --- schema translation -------------------------------------------------------

def test_mcp_schemas_become_api_schemas():
    """fastmcp calls it 'parameters', the API calls it 'input_schema'. Deriving
    them from the server means a signature change cannot silently diverge from
    what the model is told."""
    fake = [SimpleNamespace(name="t", description="d",
                            parameters={"type": "object", "properties": {}})]
    out = anthropic_tool_schemas(fake)
    assert out == [{"name": "t", "description": "d",
                    "input_schema": {"type": "object", "properties": {}}}]


def test_the_verdict_tool_offers_exactly_the_known_verdicts():
    enum = SUBMIT_VERDICT_TOOL["input_schema"]["properties"]["verdict"]["enum"]
    assert enum == VERDICT_VALUES


def test_the_signal_description_omits_absent_fields():
    text = describe_signal(sig())
    assert "period" not in text
    assert "RA" in text and "Dec" in text


def test_the_signal_description_includes_what_is_present():
    text = describe_signal(sig(period_days=6.27, depth_ppm=321.0))
    assert "6.27" in text and "321" in text


# --- the loop -----------------------------------------------------------------

def test_a_direct_verdict_ends_the_run():
    client = ScriptedClient([[verdict_block("known", 0.95, "pi Men c matched")]])
    run = run_agent(sig(), client, [], noop_tool)

    assert run.verdict == "known"
    assert run.confidence == 0.95
    assert run.iterations == 1
    assert run.stop_reason == "completed"


def test_a_tool_call_is_executed_and_fed_back():
    calls = []

    def spy(name, args):
        calls.append((name, args))
        return {"match_count": 1}

    client = ScriptedClient([
        [block_tool("check_confirmed_planets", {"ra_deg": 1.0, "dec_deg": 2.0})],
        [verdict_block("known")],
    ])
    run = run_agent(sig(), client, [], spy)

    assert calls == [("check_confirmed_planets", {"ra_deg": 1.0, "dec_deg": 2.0})]
    assert run.tools_called == ["check_confirmed_planets", "submit_verdict"]
    assert run.iterations == 2

    # the second request must carry the first result back
    second = client.calls[1]["messages"]
    assert any(isinstance(m, dict) and isinstance(m.get("content"), list)
               and isinstance(m["content"][0], dict)
               and m["content"][0].get("type") == "tool_result"
               for m in second)


def test_tokens_accumulate_across_turns():
    client = ScriptedClient([
        [block_tool("check_confirmed_planets", {})],
        [verdict_block()],
    ], in_tokens=1500, out_tokens=200)
    run = run_agent(sig(), client, [], noop_tool)

    assert run.input_tokens == 3000
    assert run.output_tokens == 400


def test_cost_is_computed_from_the_token_counts():
    run = AgentRun(signal_id="x", input_tokens=9_500, output_tokens=600)
    assert run.cost_usd(3.0, 15.0) == pytest.approx(0.0375, abs=1e-4)


# --- guardrails ---------------------------------------------------------------

def test_the_iteration_ceiling_stops_a_model_that_never_concludes():
    """A model that cannot decide will keep calling tools. Stopping is a
    result, not a failure."""
    client = ScriptedClient([[block_tool("check_confirmed_planets", {})]] * 20)
    run = run_agent(sig(), client, [], noop_tool, max_iterations=3)

    assert run.stop_reason == "max_iterations"
    assert run.iterations == 3
    assert run.verdict is None


def test_the_token_budget_stops_before_the_next_request():
    """Checked against the running total so the loop stops before spending
    again, not after discovering the overrun."""
    client = ScriptedClient([[block_tool("check_confirmed_planets", {})]] * 10,
                            in_tokens=5000, out_tokens=500)
    run = run_agent(sig(), client, [], noop_tool, token_budget=6000)

    # 5500 tokens after the first turn is under budget; the second turn crosses
    # it and the loop stops there rather than starting a third.
    assert run.stop_reason == "token_budget_exceeded"
    assert run.iterations == 2


def test_oversized_tool_results_are_truncated():
    def huge(name, args):
        return {"rows": ["x" * 1000] * 50}

    client = ScriptedClient([
        [block_tool("check_confirmed_planets", {})],
        [verdict_block()],
    ])
    run_agent(sig(), client, [], huge, max_result_chars=500)

    sent = next(
        m["content"][0]["content"]
        for m in reversed(client.calls[1]["messages"])
        if isinstance(m, dict) and isinstance(m.get("content"), list)
        and isinstance(m["content"][0], dict)
        and m["content"][0].get("type") == "tool_result"
    )
    assert len(sent) <= 500


def test_a_raising_tool_does_not_kill_the_loop():
    """A tool that raises would end the run. The error goes back as data."""
    def broken(name, args):
        raise RuntimeError("boom")

    client = ScriptedClient([
        [block_tool("check_aperture_contamination", {})],
        [verdict_block("insufficient")],
    ])
    run = run_agent(sig(), client, [], broken)

    assert run.verdict == "insufficient"
    sent = next(
        m["content"][0]["content"]
        for m in reversed(client.calls[1]["messages"])
        if isinstance(m, dict) and isinstance(m.get("content"), list)
        and isinstance(m["content"][0], dict)
        and m["content"][0].get("type") == "tool_result"
    )
    assert "boom" in sent


def test_an_api_failure_is_recorded_not_raised():
    run = run_agent(sig(), FailingClient(RuntimeError("rate limited")), [], noop_tool)

    assert run.stop_reason == "api_error"
    assert "rate limited" in run.error
    assert run.verdict is None


def test_prose_without_a_verdict_is_reported_as_such():
    """The model answering in text instead of submitting is a protocol failure,
    and must not be silently read as a verdict."""
    client = ScriptedClient([[block_text("I think it is probably known.")]])
    run = run_agent(sig(), client, [], noop_tool)

    assert run.stop_reason == "no_verdict_submitted"
    assert run.verdict is None


# --- what the model is told ---------------------------------------------------

def test_the_verdict_tool_is_always_offered():
    client = ScriptedClient([[verdict_block()]])
    run_agent(sig(), client, [{"name": "x", "description": "d", "input_schema": {}}],
              noop_tool)

    names = [t["name"] for t in client.calls[0]["tools"]]
    assert "submit_verdict" in names
    assert "x" in names


def test_the_system_prompt_forbids_reading_an_error_as_a_negative():
    client = ScriptedClient([[verdict_block()]])
    run_agent(sig(), client, [], noop_tool)

    system = client.calls[0]["system"].lower()
    assert "unreachable" in system
    assert "insufficient" in system


# --- verdict validation -------------------------------------------------------

def test_a_missing_verdict_is_a_failure_not_a_completed_run():
    """Regression, observed in a real pilot run: the model submitted
    confidence, reasoning and evidence with the verdict field omitted. The run
    was recorded as completed with a null verdict, which is a paid-for result
    that looks successful and is not."""
    client = ScriptedClient([[block_tool("submit_verdict", {
        "confidence": 0.97,
        "reasoning": "TOI-4329 b is catalogued here with a matching period",
        "evidence_used": ["check_confirmed_planets"],
    })]])
    run = run_agent(sig(), client, [], noop_tool)

    assert run.verdict is None
    assert run.stop_reason == "invalid_verdict"
    assert "expected one of" in run.error
    # what did arrive is kept, so the run can still be inspected
    assert run.confidence == 0.97
    assert run.reasoning


def test_a_verdict_outside_the_enum_is_rejected():
    client = ScriptedClient([[block_tool("submit_verdict", {
        "verdict": "probably_a_planet", "confidence": 0.8, "reasoning": "x",
    })]])
    run = run_agent(sig(), client, [], noop_tool)

    assert run.stop_reason == "invalid_verdict"
    assert run.verdict is None


@pytest.mark.parametrize("verdict", VERDICT_VALUES)
def test_every_documented_verdict_is_accepted(verdict):
    client = ScriptedClient([[verdict_block(verdict)]])
    run = run_agent(sig(), client, [], noop_tool)

    assert run.verdict == verdict
    assert run.stop_reason == "completed"


def test_the_verdict_field_carries_no_prose_description():
    """The field is a bare enum. A long description inside an enum field was
    what the model omitted; the explanation belongs in the tool description."""
    field = SUBMIT_VERDICT_TOOL["input_schema"]["properties"]["verdict"]
    assert set(field) == {"type", "enum"}
    assert all(v in SUBMIT_VERDICT_TOOL["description"] for v in VERDICT_VALUES)


# --- the exclusion asymmetry --------------------------------------------------

def test_the_prompt_states_that_exclusion_is_one_directional():
    """Regression: the agent returned 'contaminated' whenever a neighbour could
    produce the depth. Almost every neighbour can, so that condemns nearly
    every signal. The bound excludes; it does not accuse."""
    client = ScriptedClient([[verdict_block()]])
    run_agent(sig(), client, [], noop_tool)

    # Normalised: the prompt is wrapped in the source, so a phrase spanning a
    # line break is not contiguous in the string.
    system = " ".join(client.calls[0]["system"].split())
    assert "NOT EXCLUDED, not GUILTY" in system
    assert "Do NOT return 'contaminated' merely because a neighbour could" in system
    assert "that neighbour is EXCLUDED" in system
