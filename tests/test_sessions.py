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
