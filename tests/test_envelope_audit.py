"""H8: every tool failure carries an envelope class + one concrete correction."""

from __future__ import annotations

import pytest

from companion.tools import outcome
from companion.tools.cad_fea import (
    call_tool,
    load_precomputed_results,
    reset_cad_sessions,
)


def setup_function() -> None:
    reset_cad_sessions()


def _assert_envelope(result: dict, expected_class: str) -> None:
    assert result["ok"] is False
    assert result["error_class"] == expected_class
    # The class must be a known class from the corrections table...
    assert expected_class in outcome.CORRECTIONS
    # ...and carry exactly one concrete, non-empty correction.
    assert isinstance(result.get("correction"), str) and result["correction"].strip()


def test_unknown_tool_is_envelope_integrated():
    _assert_envelope(call_tool("nonexistent_cad_generator", {}), "unknown_tool")
    result = call_tool("nonexistent_cad_generator", {})
    assert "create_brake_pedal" in result["correction"]


@pytest.mark.parametrize(
    ("tool", "args", "expected_class"),
    [
        ("get_max_von_mises", {}, "no_results"),
        ("get_lattice_metrics", {}, "no_geometry"),
        ("apply_load_and_solve", {"force_n": 100}, "no_geometry"),
    ],
)
def test_state_dependent_failures_are_envelope_integrated(
    tool, args, expected_class
):
    _assert_envelope(call_tool(tool, args), expected_class)


def test_load_precomputed_missing_case_is_envelope_integrated(monkeypatch, tmp_path):
    from companion.config import get_settings

    monkeypatch.setattr(get_settings(), "results_dir", tmp_path)
    result = load_precomputed_results("definitely_not_a_case")
    _assert_envelope(result, "bad_params")
    assert "case=auto" in result["correction"]


def test_function_level_bad_web_type_is_envelope_integrated():
    """Direct function calls (bypassing the H3 boundary) still fail with a
    classed, corrected payload — defense in depth."""
    from companion.tools.cad_fea import create_brake_pedal

    result = create_brake_pedal(web_type="zigzag", open_gui=False)
    _assert_envelope(result, "bad_params")
    assert "fcc" in result["correction"]
