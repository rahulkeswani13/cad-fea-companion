"""H2: token metering — per-run usage, session totals, provider extraction."""

from __future__ import annotations

from types import SimpleNamespace

from langgraph.checkpoint.memory import MemorySaver

from companion.agent.graph import (
    build_graph,
    record_session_usage,
    reset_token_sessions,
    run_agent,
    session_usage,
)
from companion.llm.providers import AgentTurn, extract_usage
from tests.fakes import ScriptedLLMProvider, tc


def _graph(llm):
    return build_graph(
        llm=llm,
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
    )


def test_extract_usage_reads_metadata():
    msg = SimpleNamespace(
        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
    )
    assert extract_usage(msg) == {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
    }


def test_extract_usage_missing_degrades_to_none():
    assert extract_usage(SimpleNamespace()) is None
    assert extract_usage(SimpleNamespace(usage_metadata={})) is None
    assert extract_usage(SimpleNamespace(usage_metadata={"input_tokens": "x"})) is None


def test_run_agent_reports_per_run_usage_summed_over_llm_calls():
    reset_token_sessions()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(
                content="create",
                tool_calls=[tc("create_cantilever")],
                usage={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110},
            ),
            AgentTurn(
                content="solve",
                tool_calls=[tc("apply_load_and_solve", {"force_n": 100})],
                usage={"input_tokens": 200, "output_tokens": 20, "total_tokens": 220},
            ),
            AgentTurn(
                content="done",
                usage={"input_tokens": 50, "output_tokens": 5, "total_tokens": 55},
            ),
        ]
    )
    out = run_agent("create and solve", thread_id="usage-run", graph=_graph(llm))
    assert out["usage"] == {
        "input_tokens": 350,
        "output_tokens": 35,
        "total_tokens": 385,
    }


def test_run_agent_without_llm_reports_none_usage(monkeypatch):
    from companion.config import Settings
    from companion.agent.graph import build_graph as bg
    from tests.fakes import StubTools

    # Force the key-less path even when the local .env carries a real key.
    monkeypatch.setattr(Settings, "llm_configured", lambda self: False)
    g = bg(
        call_tool_fn=StubTools(),
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
    )
    out = run_agent("create a brake pedal and solve it", thread_id="usage-keyless", graph=g)
    assert out["usage"] is None


def test_session_usage_totals_per_thread():
    reset_token_sessions()
    record_session_usage("t1", {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})
    record_session_usage("t1", {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6})
    record_session_usage("t2", {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10})
    record_session_usage("t3", None)  # no-op
    snap = session_usage()
    assert snap["threads"]["t1"] == {
        "input_tokens": 15,
        "output_tokens": 3,
        "total_tokens": 18,
        "turns": 2,
    }
    assert snap["total"]["total_tokens"] == 28
    assert snap["total"]["turns"] == 3
    reset_token_sessions()
    assert session_usage() == {"threads": {}, "total": {k: 0 for k in (
        "input_tokens", "output_tokens", "total_tokens", "turns"
    )}}


def test_run_agent_records_session_totals():
    reset_token_sessions()
    llm = ScriptedLLMProvider(
        turns=[AgentTurn(content="hi", usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})]
    )
    run_agent("what is 6061 yield?", thread_id="usage-session", graph=_graph(llm))
    snap = session_usage()
    assert snap["threads"]["usage-session"]["turns"] == 1
    assert snap["threads"]["usage-session"]["total_tokens"] == 12
    reset_token_sessions()
