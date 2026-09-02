"""H3: canonical pydantic tool schemas — generation, boundary, derivation."""

from __future__ import annotations

import json

from companion.agent import tools as agent_tools
from companion.tools import design_program as dp
from companion.tools.cad_fea import TOOL_SPECS, call_tool, get_state, reset_cad_sessions
from companion.tools.tool_schemas import (
    TOOL_REGISTRY,
    build_tool_specs,
    numeric_param_ranges,
    validate_tool_args,
)


def setup_function() -> None:
    reset_cad_sessions()


def test_tool_specs_shape_and_order():
    names = [spec["name"] for spec in TOOL_SPECS]
    assert names == [entry.name for entry in TOOL_REGISTRY]
    assert len(names) == len(set(names))
    for spec in TOOL_SPECS:
        assert set(spec) == {"name", "description", "parameters"}
        assert isinstance(spec["description"], str) and spec["description"]
        schema = spec["parameters"]
        assert schema.get("type") == "object"
        assert "properties" in schema
        # Wire format must be JSON-serializable (system prompt embeds it).
        json.dumps(spec)


def test_schema_generation_is_stable():
    assert build_tool_specs() == build_tool_specs() == TOOL_SPECS


def test_ranges_and_defaults_live_in_the_schema():
    by_name = {spec["name"]: spec["parameters"] for spec in TOOL_SPECS}
    uav = by_name["create_uav_arm"]["properties"]
    assert uav["strut_radius_mm"]["minimum"] == 1.5
    assert uav["strut_radius_mm"]["maximum"] == 4.0
    assert uav["arm_length_mm"]["default"] == 180.0
    assert uav["web_type"]["enum"] == ["solid", "xtruss"]
    pedal = by_name["create_brake_pedal"]["properties"]
    assert pedal["cell_size_mm"]["minimum"] == 5.0
    assert pedal["cell_size_mm"]["maximum"] == 40.0
    cant = by_name["create_cantilever"]["properties"]
    assert cant["length_mm"]["minimum"] == 10.0
    assert cant["height_mm"]["maximum"] == 50.0


def test_agent_tools_reexport_is_the_canonical_model():
    assert agent_tools.CreateUavArmArgs.__module__ == "companion.tools.tool_schemas"


def test_boundary_rejects_out_of_range_create_args():
    result = call_tool(
        "create_uav_arm", {"web_type": "xtruss", "strut_radius_mm": 0.8}
    )
    assert result["ok"] is False
    assert result["error_class"] == "bad_params"
    assert "strut_radius_mm" in result["error"]
    assert "1.5" in result["error"]
    assert result.get("correction")
    assert result["receipt"]["tool"] == "create_uav_arm"
    # Rejected at the boundary: no session state was touched.
    assert get_state() == {"geometry": None, "results": None}


def test_boundary_rejects_each_program_floor():
    for name, args, field in (
        ("create_brake_pedal", {"cell_size_mm": 2.0}, "cell_size_mm"),
        ("create_cantilever", {"length_mm": 1000.0}, "length_mm"),
        ("create_cantilever", {"height_mm": 0.5}, "height_mm"),
        ("create_uav_arm", {"arm_length_mm": 100.0}, "arm_length_mm"),
    ):
        result = call_tool(name, args)
        assert result["ok"] is False, (name, args)
        assert result["error_class"] == "bad_params", (name, args)
        assert field in result["error"]


def test_boundary_accepts_in_range_and_coerces_strings():
    result = call_tool("create_cantilever", {"length_mm": "100"})
    assert result["ok"] is True
    assert result["length_mm"] == 100.0


def test_boundary_rejects_bad_web_type():
    result = call_tool("create_brake_pedal", {"web_type": "zigzag"})
    assert result["ok"] is False
    assert result["error_class"] == "bad_params"
    assert result.get("correction")


def test_validate_tool_args_passthrough_unknown_tool():
    # Unknown-tool handling lives at dispatch (H8), not in arg validation.
    assert validate_tool_args("nonexistent_tool", {}) is None


def test_param_specs_derived_from_models():
    assert dp.PARAM_SPECS == numeric_param_ranges()
    assert dp.PARAM_SPECS == {
        "brake_pedal": {"cell_size_mm": (5.0, 40.0), "strut_radius_mm": (1.0, 5.0)},
        "cantilever": {
            "length_mm": (10.0, 500.0),
            "width_mm": (2.0, 100.0),
            "height_mm": (1.0, 50.0),
        },
        "uav_arm": {
            "arm_length_mm": (120.0, 320.0),
            "cell_size_mm": (6.0, 30.0),
            "strut_radius_mm": (1.5, 4.0),
        },
    }


def test_program_preflight_still_rejects_via_derived_specs():
    failure = dp.preflight("uav_arm", {"strut_radius_mm": 0.8})
    assert failure is not None
    assert failure["error_class"] == "bad_params"
    assert "1.5" in failure["error"]
