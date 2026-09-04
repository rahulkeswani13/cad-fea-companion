"""Proving cases: human-in-the-loop interrupt before FreeCAD tools."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from companion.agent.graph import build_graph, run_agent
from companion.llm.providers import AgentTurn
from tests.fakes import ScriptedLLMProvider, StubTools, tc


def test_hitl_interrupt_before_freecad_tool():
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="create", tool_calls=[tc("create_cantilever")]),
            AgentTurn(content="Cantilever created after approval.", tool_calls=[]),
        ]
    )
    g = build_graph(
        llm=llm,
        call_tool_fn=tools,
        checkpointer=MemorySaver(),
        require_tool_confirm=True,
    )
    tid = "hitl-approve"
    out1 = run_agent("create cantilever", thread_id=tid, graph=g)
    assert out1["interrupted"] is True
    assert tools.names == []  # not executed yet

    out2 = run_agent(thread_id=tid, resume=True, graph=g)
    assert out2["interrupted"] is False
    assert "create_cantilever" in tools.names
    assert out2["cad_geometry"] is not None


def test_hitl_reject_skips_tool():
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="create", tool_calls=[tc("create_cantilever")]),
            AgentTurn(content="Cancelled by user.", tool_calls=[]),
        ]
    )
    g = build_graph(
        llm=llm,
        call_tool_fn=tools,
        checkpointer=MemorySaver(),
        require_tool_confirm=True,
    )
    tid = "hitl-reject"
    out1 = run_agent("create cantilever", thread_id=tid, graph=g)
    assert out1["interrupted"] is True

    out2 = run_agent(thread_id=tid, resume=False, graph=g)
    assert tools.names == []
    assert out2["interrupted"] is False
    text = (out2["answer"] or "").lower()
    assert "cancel" in text or any(
        (r.get("result") or {}).get("cancelled") for r in out2.get("tool_results") or []
    )


def test_hitl_runtime_toggle_flips_gate_without_rebuild():
    """ADR-016: with no explicit require_tool_confirm, the graph follows the
    runtime toggle on every tool-node visit — flipping it affects the same
    compiled graph immediately, mid-session included."""
    from companion.agent import confirm

    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="create", tool_calls=[tc("create_cantilever")]),
            AgentTurn(content="Cantilever created after approval.", tool_calls=[]),
            AgentTurn(content="another", tool_calls=[tc("create_cantilever")]),
            AgentTurn(content="Cantilever created, auto-run.", tool_calls=[]),
        ]
    )
    g = build_graph(llm=llm, call_tool_fn=tools, checkpointer=MemorySaver())
    tid = "hitl-runtime-toggle"
    confirm.set_require_tool_confirm(True)
    try:
        out1 = run_agent("create cantilever", thread_id=tid, graph=g)
        assert out1["interrupted"] is True
        assert tools.names == []

        out2 = run_agent(thread_id=tid, resume=True, graph=g)
        assert out2["interrupted"] is False
        assert tools.names == ["create_cantilever"]

        # Flip OFF: same compiled graph, same session — tools now auto-run.
        confirm.set_require_tool_confirm(False)
        out3 = run_agent("create another cantilever", thread_id=tid, graph=g)
        assert out3["interrupted"] is False
        assert tools.names == ["create_cantilever", "create_cantilever"]
    finally:
        confirm.reset_require_tool_confirm()
