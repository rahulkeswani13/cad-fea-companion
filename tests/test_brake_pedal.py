"""Brake-pedal tools without requiring FreeCAD GUI success."""

from __future__ import annotations

from pathlib import Path

import pytest

from companion.config import get_settings
from companion.tools import brake_pedal as bp
from companion.tools.cad_fea import (
    _STATE,
    call_tool,
    compare_brake_pedal_variants,
    create_brake_pedal,
    get_lattice_metrics,
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


def test_create_brake_pedal_memory_ok(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    result = create_brake_pedal(web_type="xtruss", open_gui=False)
    assert result["ok"] is True
    assert result["part"] == "brake_pedal"
    assert result["web_type"] == "xtruss"
    assert result["relative_density"] < 1.0
    assert result["mass_kg"] > 0


def test_bcc_alias_maps_to_xtruss(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    result = create_brake_pedal(web_type="bcc", open_gui=False)
    assert result["ok"] is True
    assert result["web_type"] == "xtruss"


def test_get_lattice_metrics_and_compare(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    create_brake_pedal(web_type="solid", open_gui=False)
    metrics = get_lattice_metrics()
    assert metrics["ok"] is True
    assert metrics["part"] == "brake_pedal"
    assert metrics["relative_density"] == 1.0

    cmp = compare_brake_pedal_variants()
    assert cmp["ok"] is True
    assert len(cmp["variants"]) == 3
    assert cmp["recommendation"]["web_type"] in {"solid", "xtruss", "fcc"}
    assert float(cmp["recommendation"]["safety_factor_vs_yield"]) >= 1.5


def test_apply_load_pedal_uses_defaults(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    create_brake_pedal(web_type="xtruss", open_gui=False)
    result = call_tool("apply_load_and_solve", {"open_gui": False})
    assert result["ok"] is True
    assert result["part"] == "brake_pedal"
    assert result["force_n"] == bp.DEFAULT_FORCE_N
    assert result["max_von_mises_mpa"] is not None


def test_load_precomputed_brake_xtruss():
    out = load_precomputed_results(case="brake_xtruss")
    assert out["ok"] is True
    assert out["results"]["part"] == "brake_pedal"
    assert out["results"]["web_type"] == "xtruss"
    assert out["results"]["max_von_mises_mpa"] is not None


def test_load_precomputed_brake_bcc_alias():
    out = load_precomputed_results(case="brake_bcc")
    assert out["ok"] is True
    assert out["results"]["web_type"] == "xtruss"


def test_invalid_web_type():
    bad = create_brake_pedal(web_type="gyroid", open_gui=False)
    assert bad["ok"] is False


def test_brake_pedal_generator_api():
    gen = bp.BrakePedalLatticeGenerator(web_type="fcc")
    geo = gen.build_geometry()
    assert geo["web_type"] == "fcc"
    lat = gen.apply_lattice("xtruss")
    assert lat["web_type"] == "xtruss"
    fem = gen.setup_fem(force_n=500.0)
    assert fem["force_n"] == 500.0


def test_get_max_von_mises_does_not_borrow_other_part(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    create_brake_pedal(web_type="xtruss", open_gui=False)
    out = get_max_von_mises()
    assert out["ok"] is False
    assert out.get("part") == "brake_pedal"


def test_solve_does_not_overwrite_golden_precomputed(monkeypatch):
    golden = ROOT / "data" / "results" / "brake_pedal_xtruss_precomputed.json"
    before = golden.read_bytes()
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    create_brake_pedal(web_type="xtruss", open_gui=False)
    result = call_tool("apply_load_and_solve", {"force_n": 999, "open_gui": False})
    assert result["ok"] is True
    assert golden.read_bytes() == before
    # Written to the (test-isolated) workspace, never the golden results dir.
    assert str(get_settings().workspace_dir) in str(result.get("results_path") or "")
