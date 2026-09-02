"""H14: router↔LLM handoff contract — who plans the next tool, pinned.

The HeuristicRouter assists the LLM path only when the LLM omits tools on
the FIRST agent visit of a run and the message carries CAD tool intent. The
offline (no-LLM) path always routes. These tests exist so a refactor cannot
silently change who plans.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from companion.agent.graph import build_graph, run_agent
from companion.config import Settings
from companion.llm.providers import AgentTurn
from tests.fakes import ScriptedLLMProvider, StubTools, tc


def _graph(llm=None, call_tool_fn=None, **kwargs):
    return build_graph(
        llm=llm,
        call_tool_fn=call_tool_fn or StubTools(),
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
        **kwargs,
    )


def test_llm_tools_win_on_first_visit():
    """LLM proposes tools → the router must not inject or replace anything."""
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="creating", tool_calls=[tc("create_cantilever")]),
            AgentTurn(content="done", tool_calls=[]),
        ]
    )
    out = run_agent(
        "create a cantilever and solve 100 N",
        thread_id="handoff-llm-wins",
        graph=_graph(llm, call_tool_fn=tools),
    )
    assert tools.names == ["create_cantilever"]
    assert out["answer"] == "done"


def test_silent_llm_with_cad_intent_gets_router_assist():
    """LLM omits tools on first visit + CAD intent → the router plans."""
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[AgentTurn(content="I will not call tools.", tool_calls=[])]
    )
    run_agent(
        "create a cantilever beam",
        thread_id="handoff-assist",
        graph=_graph(llm, call_tool_fn=tools),
    )
    assert tools.names == ["create_cantilever"]


def test_router_never_assists_after_first_visit():
    """Silent LLM on a SECOND visit → no assist; the loop ends."""
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="check", tool_calls=[tc("get_max_von_mises")]),
            AgentTurn(content="still silent", tool_calls=[]),
        ]
    )
    out = run_agent(
        "what is the max von Mises?",
        thread_id="handoff-second-visit",
        graph=_graph(llm, call_tool_fn=tools),
    )
    assert tools.names == ["get_max_von_mises"]
    assert out["agent_visits"] == 2
    assert out["tool_calls"] == []


def test_no_cad_intent_no_assist():
    """Silent LLM + docs question → nothing runs; the LLM text is the answer."""
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[AgentTurn(content="Al 6061-T6 yields around 276 MPa.", tool_calls=[])]
    )
    out = run_agent(
        "What is the yield strength of aluminum 6061-T6?",
        thread_id="handoff-docs",
        graph=_graph(llm, call_tool_fn=tools),
    )
    assert tools.names == []
    assert out["answer"] == "Al 6061-T6 yields around 276 MPa."


def test_offline_path_always_routes():
    """No LLM at all → the router plans directly (heuristic_fallback, default on)."""
    tools = StubTools()
    g = build_graph(
        call_tool_fn=tools,
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
        settings=Settings(gemini_api_key=""),
    )
    run_agent(
        "create a cantilever and apply 100 N and solve",
        thread_id="handoff-offline",
        graph=g,
    )
    assert tools.names == ["create_cantilever", "apply_load_and_solve"]
