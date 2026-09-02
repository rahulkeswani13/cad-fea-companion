"""Per-thread CAD session isolation."""

from __future__ import annotations

from companion.tools.cad_fea import (
    cad_thread_scope,
    create_brake_pedal,
    create_cantilever,
    get_state,
    reset_cad_sessions,
)


def setup_function() -> None:
    reset_cad_sessions()


def test_two_threads_keep_separate_geometry(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    with cad_thread_scope("thread-a"):
        create_brake_pedal(web_type="xtruss", open_gui=False)
        assert get_state()["geometry"]["part"] == "brake_pedal"
    with cad_thread_scope("thread-b"):
        create_cantilever(open_gui=False)
        assert get_state()["geometry"]["part"] == "cantilever"
    with cad_thread_scope("thread-a"):
        assert get_state()["geometry"]["part"] == "brake_pedal"


def test_session_and_graph_state_agree(monkeypatch):
    """H4: the CAD session stays authoritative; sync_cad_state mirrors it.

    Runs the real dispatch path (call_tool, no FreeCAD) so creates/solves
    commit into _STATE exactly like production, then asserts graph output
    and session state agree.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from companion.agent.graph import build_graph, run_agent
    from companion.config import Settings
    from companion.tools.cad_fea import call_tool

    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    g = build_graph(
        call_tool_fn=call_tool,
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
        settings=Settings(gemini_api_key=""),
    )
    tid = "consistency-1"
    out = run_agent(
        "create a cantilever and apply 100 N and solve",
        thread_id=tid,
        graph=g,
    )
    assert out["cad_geometry"] is not None
    assert out["cad_results"] is not None
    with cad_thread_scope(tid):
        session = get_state()
    assert session["geometry"]["part"] == out["cad_geometry"]["part"] == "cantilever"
    assert (
        session["results"]["max_von_mises_mpa"]
        == out["cad_results"]["max_von_mises_mpa"]
    )


def test_graph_cad_state_survives_followup_turn(monkeypatch):
    """H4: multi-turn — graph cad fields come from the session each turn."""
    from langgraph.checkpoint.memory import MemorySaver

    from companion.agent.graph import build_graph, run_agent
    from companion.config import Settings
    from companion.tools.cad_fea import call_tool

    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    g = build_graph(
        call_tool_fn=call_tool,
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
        settings=Settings(gemini_api_key=""),
    )
    tid = "consistency-2"
    first = run_agent("create a cantilever beam", thread_id=tid, graph=g)
    second = run_agent("now show me the lattice metrics", thread_id=tid, graph=g)
    assert first["cad_geometry"]["part"] == "cantilever"
    assert second["cad_geometry"]["part"] == "cantilever"
    with cad_thread_scope(tid):
        assert get_state()["geometry"]["part"] == "cantilever"
