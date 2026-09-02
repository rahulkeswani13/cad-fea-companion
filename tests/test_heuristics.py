"""H6: HeuristicRouter module + heuristic_fallback setting."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from companion.agent.graph import _heuristic_tools, build_graph, run_agent
from companion.agent.heuristics import HeuristicRouter
from companion.config import Settings
from tests.fakes import StubTools


def test_router_plans_pedal_create():
    router = HeuristicRouter()
    calls = router.plan_tools("Create an X-truss lattice brake pedal")
    assert calls[0]["name"] == "create_brake_pedal"
    assert calls[0]["args"]["web_type"] == "xtruss"


def test_router_rag_question_plans_nothing():
    router = HeuristicRouter()
    q = "What yield strength should I assume for aluminum 6061-T6?"
    assert router.plan_tools(q) == []
    assert router.plan(q, None, None, []) == []


def test_router_wrapper_parity():
    message = "Create a cantilever 100x20x5 mm and solve with 100 N"
    router = HeuristicRouter()
    assert _heuristic_tools(message) == router.plan_tools(message)


def test_heuristic_fallback_defaults_on():
    settings = Settings(gemini_api_key="")
    assert settings.heuristic_fallback is True


def test_fallback_disabled_means_no_tool_calls():
    g = build_graph(
        call_tool_fn=StubTools(),
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
        settings=Settings(gemini_api_key="", heuristic_fallback=False),
    )
    out = run_agent(
        "create a cantilever and solve 100 N",
        thread_id="fallback-off",
        graph=g,
    )
    assert out["tool_calls"] == []
    assert out["tool_results"] == []
    assert "heuristic fallback" in (out["answer"] or "").lower()
