"""Proving cases: checkpointer memory + thread isolation."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from companion.agent.graph import build_graph, run_agent
from companion.llm.providers import AgentTurn
from tests.fakes import ScriptedLLMProvider, StubTools, tc


def test_memory_multiturn_stress_followup():
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="create", tool_calls=[tc("create_cantilever")]),
            AgentTurn(
                content="solve",
                tool_calls=[tc("apply_load_and_solve", {"force_n": 100})],
            ),
            AgentTurn(content="Created and solved. Stress ~120 MPa.", tool_calls=[]),
            AgentTurn(content="check", tool_calls=[tc("get_max_von_mises")]),
            AgentTurn(
                content="No — max von Mises is about 120 MPa, which is above 50 MPa.",
                tool_calls=[],
            ),
        ]
    )
    g = build_graph(
        llm=llm,
        call_tool_fn=tools,
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
    )
    tid = "mem-followup"
    run_agent(
        "Create 100x20x5 mm cantilever and apply 100 N tip load and solve",
        thread_id=tid,
        graph=g,
    )
    out2 = run_agent(
        "Is max von Mises under 50 MPa?",
        thread_id=tid,
        graph=g,
    )
    assert "get_max_von_mises" in tools.names
    answer = (out2["answer"] or "").lower()
    assert any(k in answer for k in ("120", "50", "no", "above", "not"))


def test_memory_thread_isolation():
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="create", tool_calls=[tc("create_cantilever", {"length_mm": 100})]),
            AgentTurn(content="beam ready", tool_calls=[]),
            AgentTurn(content="I have no geometry in this thread yet.", tool_calls=[]),
        ]
    )
    g = build_graph(
        llm=llm,
        call_tool_fn=tools,
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
    )
    out_a = run_agent("create cantilever", thread_id="thread-A", graph=g)
    assert out_a["cad_geometry"] is not None

    out_b = run_agent("what geometry do we have?", thread_id="thread-B", graph=g)
    # Thread B must not inherit thread A's cad_geometry from the checkpointer
    assert out_b.get("cad_geometry") in (None, {})
    # And must not have run create on B
    assert tools.names.count("create_cantilever") == 1
