"""F03 pre-mesh B-Rep validation gate: host gate, script wiring, headless probes.

Core tests are memory-only (zero FreeCAD). The two probe tests are skipif-guarded
on FreeCADCmd being present and run headless brake-pedal only (no GUI).
"""

from __future__ import annotations

import math

import pytest

from companion.tools import brake_pedal as bp
from companion.tools import outcome
from companion.tools import validate
from companion.tools.cad_fea import call_tool, create_brake_pedal, reset_cad_sessions
from companion.tools.freecad_runtime import find_freecad_cmd, run_freecad_python

needs_freecad = pytest.mark.skipif(
    find_freecad_cmd() is None, reason="FreeCADCmd not available"
)


def setup_function() -> None:
    reset_cad_sessions()


def test_nonpositive_strut_rejected_at_boundary():
    """H3: out-of-range args hard-reject at the pydantic boundary (bad_params)
    before the tool function — the F03 B-Rep gate below still covers
    in-range-but-degenerate geometry."""
    result = call_tool(
        "create_brake_pedal", {"web_type": "xtruss", "strut_radius_mm": 0}
    )
    assert result["ok"] is False
    assert result["error_class"] == "bad_params"
    assert result["correction"]
    assert result["receipt"]["tool"] == "create_brake_pedal"


def test_nonpositive_strut_still_gated_at_function_level():
    result = create_brake_pedal(web_type="xtruss", strut_radius_mm=0)
    assert result["ok"] is False
    assert result["error_class"] == "geometry_invalid"
    assert result["validation"]["stage"] == "params_nonpositive"
    assert result["validation"]["checks"]["strut_radius_mm"] == 0


def test_nan_cell_size_rejected():
    """NaN fails the range check (all NaN comparisons are False) at the
    boundary, mirroring ADR-004's preflight NaN rule."""
    result = call_tool(
        "create_brake_pedal", {"web_type": "xtruss", "cell_size_mm": math.nan}
    )
    assert result["ok"] is False
    assert result["error_class"] == "bad_params"
    assert result["correction"]


def test_generic_param_gate_reports_only_bad_values():
    failure = validate.validate_geometry_payload(
        {"length_mm": -1.0, "width_mm": 10.0, "height_mm": 5.0}
    )
    assert failure is not None
    assert failure["validation"]["stage"] == "params_nonpositive"
    assert failure["validation"]["checks"] == {"length_mm": -1.0}
    assert "length_mm" in failure["error"]


def test_valid_params_pass_host_gate():
    assert (
        validate.validate_geometry_payload(
            {"cell_size_mm": 15.0, "strut_radius_mm": 2.5}
        )
        is None
    )


def test_classify_geometry_invalid():
    assert (
        outcome.classify_error(
            "geometry validation failed at stage brep_invalid (part=brake_pedal)"
        )
        == "geometry_invalid"
    )
    assert (
        outcome.classify_error("Final_Pedal.isValid() returned False")
        == "geometry_invalid"
    )
    assert "geometry_invalid" in outcome.CORRECTIONS


def test_snippet_contains_hard_stages():
    for stage in (
        "shape_null",
        "brep_invalid",
        "volume_nonpositive",
        "bbox_degenerate",
        "passed",
    ):
        assert f'"{stage}"' in validate.FREECAD_VALIDATION_SNIPPET


def test_pedal_scripts_gate_before_export_and_gmsh():
    geo = bp.build_geometry_script("xtruss", 15.0, 2.5, "s.step", "s.stl", "s.FCStd")
    assert "_vstage" in geo
    assert geo.index("_vstage") < geo.index("Part.export")
    fem = bp.build_fem_script("xtruss", 15.0, 2.5, 500.0, 5.0, "fem.FCStd")
    assert fem.index("_vstage") < fem.index("makeMeshGmsh")
    # Success payloads carry the validation block.
    assert '"validation": validation' in geo
    assert '"validation": validation' in fem


def test_generated_scripts_compile():
    for script in (
        bp.build_geometry_script("xtruss", 15.0, 2.5, "s.step", "s.stl", "s.FCStd"),
        bp.build_geometry_script("solid", 15.0, 2.5, "s.step", "s.stl", "s.FCStd"),
        bp.build_fem_script("xtruss", 15.0, 2.5, 500.0, 5.0, "fem.FCStd"),
    ):
        compile(script, "<generated>", "exec")


@needs_freecad
def test_gate_fires_on_invalid_brep_headless():
    probe = (
        "import json\n"
        "import FreeCAD as App\n"
        "import Part\n"
        + validate.FREECAD_VALIDATION_SNIPPET
        # Gate call is indented for a try block, matching the real scripts.
        + "\ntry:\n"
        "    body = Part.Shape()\n"
        "    rho = None\n"
        "    web_type = 'solid'\n"
        + validate.gate_call_snippet("probe", 1000.0)
        + "except Exception:\n"
        "    import traceback\n"
        "    print('COMPANION_JSON:' + json.dumps({'ok': False, 'error': traceback.format_exc()}))\n"
    )
    assert "gmsh" not in probe.lower()
    result = run_freecad_python(probe, timeout=60)
    assert result["ok"] is False
    assert result["error_class"] == "geometry_invalid"
    assert result["validation"]["stage"] in ("brep_invalid", "shape_null")
    assert "Traceback" not in result.get("error", "")


@needs_freecad
def test_valid_pedal_reports_passed_stage_headless():
    result = create_brake_pedal(web_type="xtruss", open_gui=False)
    assert result["ok"] is True
    assert result["validation"]["stage"] == "passed"
    assert result["validation"]["checks"]["volume_mm3"] > 0
    assert result["validation"]["checks"]["is_valid"] is True
    assert isinstance(result["validation"]["warnings"], list)
