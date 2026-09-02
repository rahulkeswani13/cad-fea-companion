"""F02 outcome envelope: compact results, corrections, receipts, no raw tracebacks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from companion.agent.graph import _cad_state_blob
from companion.tools import outcome
from companion.tools.cad_fea import call_tool, reset_cad_sessions


def setup_function() -> None:
    reset_cad_sessions()


def test_success_envelope_has_receipt_and_domain_keys(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    result = call_tool("create_brake_pedal", {"web_type": "xtruss", "open_gui": False})
    assert result["ok"] is True
    # Flat-additive: domain keys stay top-level.
    assert result["part"] == "brake_pedal"
    assert result["web_type"] == "xtruss"
    receipt = result["receipt"]
    assert receipt["tool"] == "create_brake_pedal"
    assert receipt["elapsed_s"] >= 0
    assert "geometry_replaced" in receipt["changed"]
    # Successes carry no error fields.
    assert "error_class" not in result
    assert "correction" not in result


def test_observation_tool_receipt_changed_empty():
    result = call_tool("compare_brake_pedal_variants", {})
    assert result["ok"] is True
    assert result["receipt"]["tool"] == "compare_brake_pedal_variants"
    assert result["receipt"]["changed"] == []


def test_unknown_tool_failure_shape():
    result = call_tool("no_such_tool", {})
    assert result["ok"] is False
    assert result["error_class"] == "unknown_tool"
    assert result["correction"]
    assert result["receipt"]["tool"] == "no_such_tool"
    assert "Traceback" not in json.dumps(result)


def test_bad_params_failure_shape():
    result = call_tool("create_brake_pedal", {"web_type": "zigzag"})
    assert result["ok"] is False
    assert result["error_class"] == "bad_params"
    assert result["correction"]
    # H3: boundary validation reports the field and its allowed values.
    assert "web_type" in result["error"] and "'xtruss'" in result["error"]


def test_no_geometry_failure_shape():
    result = call_tool("apply_load_and_solve", {"force_n": 100})
    assert result["ok"] is False
    assert result["error_class"] == "no_geometry"
    assert "create" in result["correction"]


def test_no_results_failure_shape():
    result = call_tool("get_max_von_mises", {})
    assert result["ok"] is False
    assert result["error_class"] == "no_results"
    assert "apply_load_and_solve" in result["correction"]


def test_envelope_strips_raw_diagnostics():
    raw = {
        "ok": False,
        "error": (
            "Traceback (most recent call last):\n"
            '  File "/tmp/fem.py", line 12, in <module>\n'
            "RuntimeError: CalculiX finished but no von Mises results were found."
        ),
        "stdout_tail": "junk" * 500,
        "stderr_tail": "warn" * 500,
    }
    out = outcome.envelope(raw, tool="apply_load_and_solve", elapsed_s=1.5)
    assert "stdout_tail" not in out
    assert "stderr_tail" not in out
    assert "\n" not in out["error"]
    assert out["error"].endswith(
        "RuntimeError: CalculiX finished but no von Mises results were found."
    )
    assert out["error_class"] == "solve_failed"
    assert out["correction"]
    blob = json.dumps(out)
    assert "Traceback" not in blob
    assert "junk" not in blob
    assert out["debug_ref"]
    assert Path(out["debug_ref"]).name == "tool_debug.log"
    assert Path(out["debug_ref"]).exists()


def test_envelope_condenses_long_freecad_error_on_success():
    raw = {
        "ok": True,
        "part": "brake_pedal",
        "freecad_error": "FreeCADCmd failed (Traceback (most recent call last):\nboom)",
    }
    out = outcome.envelope(raw, tool="create_brake_pedal", elapsed_s=0.1)
    assert out["ok"] is True
    assert "Traceback" not in json.dumps(out)
    assert out["freecad_error"] == "boom)"
    assert out["debug_ref"]


def test_wrap_catches_exceptions_without_traceback():
    def boom(name: str, args: dict) -> dict:
        raise RuntimeError("kaboom")

    out = outcome.wrap_tool_call("apply_load_and_solve", {}, boom)
    assert out["ok"] is False
    assert out["error_class"] == "internal_error"
    assert "RuntimeError: kaboom" in out["error"]
    assert "Traceback" not in json.dumps(out)
    assert out["debug_ref"]
    assert out["receipt"]["tool"] == "apply_load_and_solve"


def test_hitl_cancelled_envelope():
    out = outcome.envelope(
        {
            "ok": False,
            "cancelled": True,
            "error": "User rejected FreeCAD tool confirmation.",
            "error_class": "user_cancelled",
        },
        tool="create_brake_pedal",
        elapsed_s=0.0,
    )
    assert out["cancelled"] is True
    assert out["error_class"] == "user_cancelled"
    assert "confirm" in out["correction"].lower()


def test_envelope_is_flat_additive():
    out = outcome.envelope(
        {"ok": True, "custom_kpi": 1.25},
        tool="t",
        elapsed_s=0.5,
        changed=["results_replaced"],
    )
    assert out["custom_kpi"] == 1.25
    assert out["receipt"]["changed"] == ["results_replaced"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Unknown tool: frobnicate", "unknown_tool"),
        ("web_type must be one of ['bcc', 'fcc']", "bad_params"),
        ("No geometry. Call create_brake_pedal first.", "no_geometry"),
        ("No results yet. Call apply_load_and_solve first.", "no_results"),
        ("FreeCADCmd not found. Install FreeCAD and retry.", "freecad_missing"),
        ("FreeCADCmd timed out after 420s", "freecad_timeout"),
        ("No COMPANION_JSON marker in FreeCAD output", "freecad_crash"),
        ("CalculiX finished but no von Mises results were found.", "solve_failed"),
        ("Gmsh produced an empty mesh", "mesh_failed"),
        ("something inexplicable", "internal_error"),
    ],
)
def test_classify_error(text: str, expected: str):
    assert outcome.classify_error(text) == expected


def test_cad_state_blob_is_compact_kpi_summary():
    blob = _cad_state_blob(
        {
            "cad_geometry": {
                "part": "cantilever",
                "length_mm": 100,
                "width_mm": 20,
                "height_mm": 5,
                "step_path": "/tmp/x.step",
                "fixed_face": "Face1 (x=0 root)",
                "load_face": "Face2 (x=L tip)",
            },
            "cad_results": {
                "ok": True,
                "part": "cantilever",
                "method": "calculix_ccx",
                "force_n": 100,
                "max_von_mises_mpa": 118.2,
                "node_count": 4210,
                "receipt": {"tool": "apply_load_and_solve", "elapsed_s": 9.1},
                "gui": {"launched": "..."},
            },
        }
    )
    parsed = json.loads(blob)
    assert parsed["geometry"]["part"] == "cantilever"
    assert parsed["results"]["max_von_mises_mpa"] == 118.2
    # Bloat stays out of the system prompt.
    assert "receipt" not in blob
    assert "gui" not in blob
    assert "node_count" not in blob
    assert "fixed_face" not in blob


def test_cad_state_blob_empty_is_none_marker():
    assert _cad_state_blob({}) == "(none)"
