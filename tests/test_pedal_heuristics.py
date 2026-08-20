"""Heuristic routing for brake-pedal lattice and cantilever prompts."""

from __future__ import annotations

from companion.agent.graph import _heuristic_next_tool, _heuristic_tools


def test_heuristic_create_xtruss_pedal():
    calls = _heuristic_tools("Create an X-truss lattice brake pedal")
    assert calls[0]["name"] == "create_brake_pedal"
    assert calls[0]["args"].get("web_type") == "xtruss"


def test_heuristic_bcc_alias_pedal():
    calls = _heuristic_tools("Create a BCC lattice brake pedal")
    assert calls[0]["name"] == "create_brake_pedal"
    assert calls[0]["args"].get("web_type") == "xtruss"


def test_heuristic_compare_pedal_variants():
    calls = _heuristic_tools(
        "Compare solid X-truss and FCC brake pedal variants and recommend the lightest"
    )
    names = [c["name"] for c in calls]
    assert "compare_brake_pedal_variants" in names


def test_heuristic_solve_pedal_creates_geometry_first():
    nxt = _heuristic_next_tool(
        "Solve the brake pedal lattice with 500 N",
        cad_geometry=None,
        cad_results=None,
        tool_results=[],
    )
    assert nxt[0]["name"] == "create_brake_pedal"
    assert nxt[0]["args"].get("web_type") == "xtruss"


def test_heuristic_relative_density_is_not_a_tool_request():
    q = "What relative density ranges are typical for lattice fills?"
    assert _heuristic_tools(q) == []
    nxt = _heuristic_next_tool(q, None, None, [])
    assert nxt == []


def test_heuristic_yield_question_is_not_a_tool_request():
    q = "What yield strength should I assume for aluminum 6061-T6?"
    assert _heuristic_tools(q) == []
    nxt = _heuristic_next_tool(q, None, None, [])
    assert nxt == []


def test_heuristic_cantilever_still_works():
    calls = _heuristic_tools("Create a cantilever 100x20x5 mm and apply 100 N tip load and solve.")
    names = [c["name"] for c in calls]
    assert "create_cantilever" in names
    assert "apply_load_and_solve" in names


def test_heuristic_create_solid_uav_arm():
    calls = _heuristic_tools("Create a solid aluminum UAV arm")
    assert calls[0]["name"] == "create_uav_arm"
    assert calls[0]["args"].get("web_type") == "solid"


def test_heuristic_create_xtruss_uav_arm():
    calls = _heuristic_tools("Create a truss UAV arm")
    assert calls[0]["name"] == "create_uav_arm"
    assert calls[0]["args"].get("web_type") == "xtruss"


def test_heuristic_uav_not_routed_to_cantilever():
    calls = _heuristic_tools("Create a quadcopter arm with 120 N tip load")
    names = [c["name"] for c in calls]
    assert "create_uav_arm" in names
    assert "create_cantilever" not in names


def test_heuristic_drone_motor_mount_routes_to_uav():
    calls = _heuristic_tools("Build a motor mount arm for a drone")
    assert calls[0]["name"] == "create_uav_arm"
