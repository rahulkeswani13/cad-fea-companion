"""UAV-arm tools (F26) without requiring FreeCAD GUI success."""

from __future__ import annotations

from pathlib import Path

import pytest

from companion.config import get_settings
from companion.tools import uav_arm as ua
from companion.tools.cad_fea import (
    _STATE,
    call_tool,
    create_uav_arm,
    get_max_von_mises,
    load_precomputed_results,
    reset_cad_sessions,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _workspace(tmp_path, monkeypatch):
    """Isolate runtime writes (precomputed JSONs, F06 run history) per test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    return tmp_path


def setup_function() -> None:
    reset_cad_sessions()
    _STATE["geometry"] = None
    _STATE["results"] = None


def test_create_uav_arm_memory_ok(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    result = create_uav_arm(web_type="xtruss", open_gui=False)
    assert result["ok"] is True
    assert result["part"] == "uav_arm"
    assert result["web_type"] == "xtruss"
    assert result["relative_density"] < 1.0
    assert result["mass_kg"] > 0


def test_create_uav_arm_solid_memory_ok(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    result = create_uav_arm(web_type="solid", open_gui=False)
    assert result["ok"] is True
    assert result["web_type"] == "solid"
    assert result["relative_density"] == 1.0


def test_uav_arm_bcc_alias_maps_to_xtruss(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    result = create_uav_arm(web_type="bcc", open_gui=False)
    assert result["ok"] is True
    assert result["web_type"] == "xtruss"


def test_uav_arm_truss_alias_maps_to_xtruss(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    result = create_uav_arm(web_type="truss", open_gui=False)
    assert result["ok"] is True
    assert result["web_type"] == "xtruss"


def test_invalid_web_type_uav_arm():
    bad = create_uav_arm(web_type="gyroid", open_gui=False)
    assert bad["ok"] is False


def test_apply_load_uav_arm_uses_defaults(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    create_uav_arm(web_type="xtruss", open_gui=False)
    result = call_tool("apply_load_and_solve", {"open_gui": False})
    assert result["ok"] is True
    assert result["part"] == "uav_arm"
    assert result["force_n"] == ua.DEFAULT_FORCE_N
    assert result["max_von_mises_mpa"] is not None


def test_load_precomputed_uav_arm_solid():
    out = load_precomputed_results(case="uav_solid")
    assert out["ok"] is True
    assert out["results"]["part"] == "uav_arm"
    assert out["results"]["web_type"] == "solid"
    assert out["results"]["max_von_mises_mpa"] is not None


def test_load_precomputed_uav_arm_xtruss():
    out = load_precomputed_results(case="uav_xtruss")
    assert out["ok"] is True
    assert out["results"]["web_type"] == "xtruss"


def test_solve_does_not_overwrite_golden_precomputed_uav(monkeypatch):
    golden = ROOT / "data" / "results" / "uav_arm_solid_precomputed.json"
    before = golden.read_bytes()
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    create_uav_arm(web_type="solid", open_gui=False)
    result = call_tool("apply_load_and_solve", {"force_n": 999, "open_gui": False})
    assert result["ok"] is True
    assert golden.read_bytes() == before
    # Written to the (test-isolated) workspace, never the golden results dir.
    assert str(get_settings().workspace_dir) in str(result.get("results_path") or "")


def test_uav_arm_generator_api():
    gen = ua.UAVArmGenerator(web_type="xtruss")
    geo = gen.build_geometry()
    assert geo["web_type"] == "xtruss"
    lat = gen.apply_lattice("solid")
    assert lat["web_type"] == "solid"
    fem = gen.setup_fem(force_n=120.0)
    assert fem["force_n"] == 120.0


def test_uav_arm_memory_geometry_has_arm_length(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    result = create_uav_arm(web_type="solid", arm_length_mm=200.0, open_gui=False)
    assert result["ok"] is True
    assert result["arm_length_mm"] == 200.0


def test_uav_arm_estimate_volume_positive():
    vols = ua.estimate_part_volume_mm3(web_type="xtruss")
    assert vols["boss_volume_mm3"] > 0
    assert vols["arm_volume_mm3"] > 0
    assert vols["chord_rails_volume_mm3"] > 0
    assert vols["ring_volume_mm3"] > 0
    assert vols["pocket_volume_mm3"] > 0
    assert vols["lattice_fill_volume_mm3"] > 0
    assert vols["volume_mm3"] > 0
    assert vols["mass_kg"] > 0
    assert 0.0 < vols["relative_density"] < 1.0


def test_uav_arm_estimate_lattice_fill_positive():
    assert ua.estimate_lattice_fill_volume_mm3() > 0


def test_uav_arm_expected_bbox_dims():
    dims = ua.expected_bbox_dims()
    assert len(dims) == 3
    assert all(d > 0 for d in dims)
    assert dims[0] > dims[1]  # arm longer than wide


def test_uav_arm_fallback_fea_result():
    fb = ua.fallback_fea_result("solid", 120.0)
    assert fb["ok"] is True
    assert fb["method"] == "precomputed_demo_estimate"
    assert fb["fallback"] is True
    assert fb["max_von_mises_mpa"] > 0
    assert fb["tip_deflection_mm"] > 0
    assert fb["safety_factor_vs_yield"] > 0


def test_uav_arm_get_max_von_mises_borrow_ok(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    create_uav_arm(web_type="xtruss", open_gui=False)
    call_tool("apply_load_and_solve", {"open_gui": False})
    out = get_max_von_mises()
    assert out["ok"] is True
    assert out["part"] == "uav_arm"
    assert out["max_von_mises_mpa"] is not None
