"""Proving cases: tool loop + CAD-in-state (vs linear one-shot graph)."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from companion.agent.graph import build_graph, run_agent
from companion.llm.providers import AgentTurn
from tests.fakes import ScriptedLLMProvider, StubTools, tc


def _graph(llm, tools: StubTools, **kwargs):
    return build_graph(
        llm=llm,
        call_tool_fn=tools,
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
        **kwargs,
    )


def test_loop_sequential_create_solve():
    """Agent creates, observes ok, then solves — not one dumped plan."""
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="creating", tool_calls=[tc("create_cantilever", {"length_mm": 100})]),
            AgentTurn(
                content="solving",
                tool_calls=[tc("apply_load_and_solve", {"force_n": 100})],
            ),
            AgentTurn(content="Done. Max stress ~120 MPa.", tool_calls=[]),
        ]
    )
    g = _graph(llm, tools)
    out = run_agent(
        "Create 100x20x5 and solve with 100 N",
        thread_id="loop-seq",
        graph=g,
    )
    assert tools.names == ["create_cantilever", "apply_load_and_solve"]
    assert out["agent_visits"] >= 3
    assert out["tools_node_visits"] >= 2
    assert "120" in (out["answer"] or "") or out["cad_results"]


def test_loop_retry_after_tool_error():
    tools = StubTools()
    tools.fail_create_times = 1
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="try create", tool_calls=[tc("create_cantilever")]),
            AgentTurn(content="retry create", tool_calls=[tc("create_cantilever")]),
            AgentTurn(content="Created successfully after retry.", tool_calls=[]),
        ]
    )
    g = _graph(llm, tools)
    out = run_agent("create cantilever", thread_id="loop-retry", graph=g)
    assert tools.names.count("create_cantilever") == 2
    assert tools.geometry is not None
    assert "retry" in (out["answer"] or "").lower() or out["cad_geometry"]


def test_loop_solve_without_geometry_recovers():
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(
                content="solve first",
                tool_calls=[tc("apply_load_and_solve", {"force_n": 100})],
            ),
            AgentTurn(content="need geometry", tool_calls=[tc("create_cantilever")]),
            AgentTurn(
                content="now solve",
                tool_calls=[tc("apply_load_and_solve", {"force_n": 100})],
            ),
            AgentTurn(content="Stress is 120 MPa.", tool_calls=[]),
        ]
    )
    g = _graph(llm, tools)
    out = run_agent("solve tip load", thread_id="loop-recover", graph=g)
    assert "create_cantilever" in tools.names
    assert tools.names.count("apply_load_and_solve") >= 2
    assert out["cad_geometry"] is not None
    assert out["cad_results"] is not None
    assert "120" in (out["answer"] or "") or out["cad_results"]["max_von_mises_mpa"] == 120


def test_cond_rag_lattice_question_skips_tools(monkeypatch):
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(
                content="Typical AM strut fills often sit around 0.15–0.40 relative density.",
                tool_calls=[],
            )
        ]
    )

    def fake_retrieve(query: str, k: int = 4):
        return [
            {
                "source": "brake_pedal_lattice.md",
                "text": "Typical AM strut fills often sit around 0.15–0.40 ρ*",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr("companion.agent.graph.retrieve", fake_retrieve)
    g = _graph(llm, tools)
    out = run_agent(
        "What relative density ranges are typical for lattice fills?",
        thread_id="rag-rd",
        graph=g,
    )
    assert tools.names == []
    assert out["tools_node_visits"] == 0
    assert "0.15" in (out["answer"] or "")


def test_cond_rag_only_skips_tools(monkeypatch):
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[AgentTurn(content="Mild steel yield is about 250 MPa.", tool_calls=[])]
    )

    def fake_retrieve(query: str, k: int = 4):
        return [
            {
                "source": "material_allowables.md",
                "text": "Mild steel typical yield ~250 MPa",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr("companion.agent.graph.retrieve", fake_retrieve)
    g = _graph(llm, tools)
    out = run_agent("What is mild steel yield?", thread_id="rag-only", graph=g)
    assert tools.names == []
    assert out["tools_node_visits"] == 0
    assert out["citations"]
    assert "250" in (out["answer"] or "")


def test_cond_reuse_geometry_no_recreate():
    tools = StubTools()
    tools.geometry = {"length_mm": 100, "width_mm": 20, "height_mm": 5, "ok": True}
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(
                content="reuse geometry",
                tool_calls=[tc("apply_load_and_solve", {"force_n": 100})],
            ),
            AgentTurn(content="Solved with existing beam.", tool_calls=[]),
        ]
    )
    g = _graph(llm, tools)
    config = {"configurable": {"thread_id": "reuse-geo"}}
    g.update_state(
        config,
        {
            "cad_geometry": tools.geometry,
            "cad_results": None,
            "tool_results": [],
            "iteration": 0,
            "agent_visits": 0,
            "tools_node_visits": 0,
        },
    )
    out = run_agent("apply 100 N and solve", thread_id="reuse-geo", graph=g)
    assert "create_cantilever" not in tools.names
    assert "apply_load_and_solve" in tools.names


def test_max_iters_stops_runaway_tools():
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="again", tool_calls=[tc("get_max_von_mises")]),
        ]
    )
    g = _graph(llm, tools, max_tool_rounds=2)
    out = run_agent("stress?", thread_id="max-iters", graph=g)
    assert out["agent_visits"] <= 3
    assert "Stopped after" in (out["answer"] or out.get("error") or "")
    assert len(tools.names) <= 2


def test_cad_state_mirrored_in_graph():
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="create", tool_calls=[tc("create_cantilever", {"length_mm": 100})]),
            AgentTurn(
                content="solve",
                tool_calls=[tc("apply_load_and_solve", {"force_n": 100})],
            ),
            AgentTurn(content="done", tool_calls=[]),
        ]
    )
    g = _graph(llm, tools)
    out = run_agent("create and solve", thread_id="cad-mirror", graph=g)
    assert out["cad_geometry"] is not None
    assert out["cad_geometry"]["length_mm"] == 100
    assert out["cad_results"] is not None
    assert out["cad_results"]["max_von_mises_mpa"] == 120.0


def test_loop_brake_pedal_create_solve_compare():
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(
                content="creating pedal",
                tool_calls=[tc("create_brake_pedal", {"web_type": "xtruss"})],
            ),
            AgentTurn(
                content="solving",
                tool_calls=[tc("apply_load_and_solve", {"force_n": 500})],
            ),
            AgentTurn(
                content="comparing",
                tool_calls=[tc("compare_brake_pedal_variants")],
            ),
            AgentTurn(
                content="X-truss is lightest with SF above 1.5.",
                tool_calls=[],
            ),
        ]
    )
    g = _graph(llm, tools)
    out = run_agent(
        "Create X-truss brake pedal lattice, solve, and compare variants",
        thread_id="pedal-loop",
        graph=g,
    )
    assert tools.names == [
        "create_brake_pedal",
        "apply_load_and_solve",
        "compare_brake_pedal_variants",
    ]
    assert out["cad_geometry"]["part"] == "brake_pedal"
    assert out["cad_results"]["max_von_mises_mpa"] == 13.8
