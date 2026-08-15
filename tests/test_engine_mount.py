"""Engine-mount tools without requiring FreeCAD GUI success."""

from __future__ import annotations

from companion.tools import engine_mount as em
from companion.tools.cad_fea import (
    _STATE,
    call_tool,
    compare_mount_variants,
    create_engine_mount,
    get_lattice_metrics,
    load_precomputed_results,
    reset_cad_sessions,
)


def setup_function() -> None:
    reset_cad_sessions()
    _STATE["geometry"] = None
    _STATE["results"] = None


def test_create_engine_mount_memory_ok(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    result = create_engine_mount(web_type="bcc", open_gui=False)
    assert result["ok"] is True
    assert result["part"] == "engine_mount"
    assert result["web_type"] == "bcc"
    assert result["relative_density"] < 1.0
    assert result["mass_kg"] > 0


def test_get_lattice_metrics_and_compare(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    create_engine_mount(web_type="solid", open_gui=False)
    metrics = get_lattice_metrics()
    assert metrics["ok"] is True
    assert metrics["relative_density"] == 1.0

    cmp = compare_mount_variants()
    assert cmp["ok"] is True
    assert len(cmp["variants"]) == 3
    assert cmp["recommendation"]["web_type"] in {"solid", "bcc", "fcc"}
    assert float(cmp["recommendation"]["safety_factor_vs_yield"]) >= 1.5


def test_apply_load_mount_uses_defaults(monkeypatch):
    monkeypatch.setattr("companion.tools.cad_fea.find_freecad_cmd", lambda: None)
    create_engine_mount(web_type="bcc", open_gui=False)
    result = call_tool("apply_load_and_solve", {})
    assert result["ok"] is True
    assert result["part"] == "engine_mount"
    assert result["force_n"] == em.DEFAULT_FORCE_N
    assert result["max_von_mises_mpa"] is not None


def test_load_precomputed_bcc():
    out = load_precomputed_results(case="bcc")
    assert out["ok"] is True
    assert out["results"]["web_type"] == "bcc"
    assert out["results"]["max_von_mises_mpa"] is not None
    assert float(out["results"]["max_von_mises_mpa"]) > 0


def test_invalid_web_type():
    bad = create_engine_mount(web_type="gyroid", open_gui=False)
    assert bad["ok"] is False
