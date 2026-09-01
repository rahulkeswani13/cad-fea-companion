"""Proving cases: stream event order for the agent loop."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from companion.agent.graph import build_graph, stream_agent
from companion.llm.providers import AgentTurn
from tests.fakes import ScriptedLLMProvider, StubTools, tc


def test_stream_event_order(monkeypatch):
    tools = StubTools()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="create", tool_calls=[tc("create_cantilever")]),
            AgentTurn(
                content="solve",
                tool_calls=[tc("apply_load_and_solve", {"force_n": 100})],
            ),
            AgentTurn(content="All done.", tool_calls=[]),
        ]
    )

    monkeypatch.setattr(
        "companion.agent.graph.retrieve_detail",
        lambda query, k=4: {
            "grounding": "strong",
            "fused": [
                {"source": "demo.md", "text": "cantilever notes", "score": 0.5}
            ],
            "tfidf": [],
            "bm25": [],
        },
    )

    g = build_graph(
        llm=llm,
        call_tool_fn=tools,
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
    )
    events = list(
        stream_agent("create and solve", thread_id="stream-order", graph=g)
    )
    nodes = [e.get("node") for e in events if e.get("type") == "node"]
    assert "retrieve" in nodes
    assert "agent" in nodes
    assert "tools" in nodes

    # First tools batch should be create; a later tools batch solve
    tool_status_events = [
        e for e in events if e.get("type") == "node" and e.get("node") == "tools"
    ]
    assert len(tool_status_events) >= 2

    finals = [e for e in events if e.get("type") == "final"]
    assert len(finals) == 1
    assert finals[0].get("cad_results") is not None
    assert tools.names == ["create_cantilever", "apply_load_and_solve"]
