"""F09 material parameter: table, aliases, citations, scaling, program edits.

All tests are memory-only (zero FreeCAD): geometry comes from the memory /
fallback paths with `find_freecad_cmd` stubbed to None, programs live in a
tmp workspace.
"""

from __future__ import annotations

import pytest

from companion.config import get_settings
from companion.tools import brake_pedal as bp
from companion.tools import cad_fea
from companion.tools import materials as mats
from companion.tools.cad_fea import call_tool, reset_cad_sessions


def setup_function() -> None:
    reset_cad_sessions()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Isolate program files + run history + runtime results in a tmp dir."""
    settings = get_settings()
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    monkeypatch.setattr(settings, "results_dir", tmp_path / "results")
    return tmp_path


@pytest.fixture
def no_freecad(monkeypatch):
    monkeypatch.setattr(cad_fea, "find_freecad_cmd", lambda: None)


EXPECTED_IDS = {"al6061t6", "al7075t6", "ti6al4v", "pa12", "steel"}


def test_table_loads_five_cited_materials():
    table = mats.load_materials()
    assert set(table) == EXPECTED_IDS
    for record in table.values():
        assert float(record["youngs_modulus_mpa"]) > 0
        assert 0.0 < float(record["poissons_ratio"]) < 0.5
        assert float(record["density_kg_m3"]) > 0
        assert float(record["yield_mpa"]) > 0
        # Every number the agent can quote traces to a source string.
        assert set(record["sources"]) == {"elasticity", "density", "yield"}
        assert all(str(s).strip() for s in record["sources"].values())


def test_alias_resolution():
    assert mats.get_material("Ti-6Al-4V")["id"] == "ti6al4v"
    assert mats.get_material("ti")["id"] == "ti6al4v"
    assert mats.get_material("TI64")["id"] == "ti6al4v"
    assert mats.get_material("titanium")["id"] == "ti6al4v"
    assert mats.get_material("Al 6061-T6")["id"] == "al6061t6"
    assert mats.get_material("6061")["id"] == "al6061t6"
    assert mats.get_material("7075")["id"] == "al7075t6"
    assert mats.get_material("nylon")["id"] == "pa12"
    assert mats.get_material("Steel-Generic")["id"] == "steel"
    assert mats.get_material("unobtainium") is None
    assert mats.get_material("") is None
    assert mats.get_material(None) is None


def test_bad_material_payload_names_every_option():
    payload = mats.bad_material_payload("unobtainium")
    assert payload["ok"] is False
    assert payload["error_class"] == "bad_params"
    assert payload["correction"]
    for mid in EXPECTED_IDS:
        assert mid in payload["correction"]


def test_default_descriptions_byte_identical():
    # Pre-F09 result strings must survive the material table unchanged.
    assert mats.describe(None) == "Al 6061-T6 approx E=69 GPa, nu=0.33"
    assert mats.describe(mats.get_material("al")) == (
        "Al 6061-T6 approx E=69 GPa, nu=0.33"
    )
    geo = bp.memory_geometry("xtruss", 15.0, 2.5, "w")
    assert geo["material"] == "Al 6061-T6 approx E=69 GPa, nu=0.33"
    assert geo["yield_mpa"] == bp.AL_YIELD_MPA


def test_docs_materials_md_stays_in_sync():
    assert mats.doc_sync_errors() == []


def test_scale_result_to_titanium():
    base = bp.fallback_fea_result("xtruss", bp.DEFAULT_FORCE_N)
    ti = mats.get_material("ti")
    scaled = mats.scale_result(base, ti, "brake_pedal")
    assert scaled["material_id"] == "ti6al4v"
    # Stress is carried over unchanged (E-independence assumption).
    assert scaled["max_von_mises_mpa"] == base["max_von_mises_mpa"]
    # mass x rho_new/rho_ref, deflection x E_ref/E_new.
    ratio_m = 4430.0 / 2700.0
    assert scaled["mass_kg"] == pytest.approx(base["mass_kg"] * ratio_m, rel=1e-3)
    assert scaled["pad_deflection_mm"] == pytest.approx(
        base["pad_deflection_mm"] * 69000.0 / 113800.0, rel=1e-3
    )
    assert scaled["safety_factor_vs_yield"] == pytest.approx(
        880.0 / base["max_von_mises_mpa"], abs=0.01
    )
    assert scaled["method"] == "precomputed_demo_estimate_scaled"
    assert scaled["scaled_from_material"] == "al6061t6"
    assert scaled["deflection_not_verified"] is False


def test_scale_result_flags_pa12_deflection():
    base = bp.fallback_fea_result("xtruss", bp.DEFAULT_FORCE_N)
    pa = mats.get_material("pa12")
    scaled = mats.scale_result(base, pa, "brake_pedal")
    assert scaled["deflection_not_verified"] is True
    assert any("NOT VERIFIED" in note for note in scaled["scaling_notes"])


def test_scale_result_same_material_is_noop():
    base = bp.fallback_fea_result("xtruss", bp.DEFAULT_FORCE_N)
    al = mats.get_material("al6061t6")
    scaled = mats.scale_result(base, al, "brake_pedal")
    assert scaled["method"] == base["method"]
    assert "scaled_from_material" not in scaled
    assert scaled["mass_kg"] == base["mass_kg"]
    assert scaled["pad_deflection_mm"] == base["pad_deflection_mm"]


def test_create_pedal_with_material(workspace, no_freecad):
    result = call_tool(
        "create_brake_pedal", {"material": "Ti-6Al-4V", "open_gui": False}
    )
    assert result["ok"] is True
    assert result["material_id"] == "ti6al4v"
    assert result["yield_mpa"] == 880.0
    al_geo = bp.memory_geometry("xtruss", 15.0, 2.5, "w")
    assert result["mass_kg"] == pytest.approx(
        al_geo["mass_kg"] * 4430.0 / 2700.0, rel=1e-3
    )
    program = call_tool("get_design_program", {"part": "brake_pedal"})
    assert program["params"]["material"] == "ti6al4v"


def test_create_rejects_unknown_material(workspace, no_freecad):
    result = call_tool("create_brake_pedal", {"material": "vibranium"})
    assert result["ok"] is False
    assert result["error_class"] == "bad_params"
    assert "ti6al4v" in result["correction"]


def test_update_program_switches_material(workspace, no_freecad):
    assert call_tool("create_brake_pedal", {"open_gui": False})["ok"]
    rev0 = call_tool("get_design_program", {"part": "brake_pedal"})["rev"]
    result = call_tool(
        "update_design_program",
        {"part": "brake_pedal", "changes": {"material": "7075"}, "open_gui": False},
    )
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["program"]["rev"] == rev0 + 1
    program = call_tool("get_design_program", {"part": "brake_pedal"})
    assert program["params"]["material"] == "al7075t6"
    assert cad_fea.get_state()["geometry"]["material_id"] == "al7075t6"


def test_update_program_noop_same_material(workspace, no_freecad):
    assert call_tool("create_brake_pedal", {"open_gui": False})["ok"]
    result = call_tool(
        "update_design_program",
        {"part": "brake_pedal", "changes": {"material": "al"}, "open_gui": False},
    )
    assert result["ok"] is True
    assert result["changed"] is False


def test_update_program_rejects_unknown_material(workspace, no_freecad):
    assert call_tool("create_brake_pedal", {"open_gui": False})["ok"]
    rev0 = call_tool("get_design_program", {"part": "brake_pedal"})["rev"]
    result = call_tool(
        "update_design_program",
        {"part": "brake_pedal", "changes": {"material": "adamantium"}},
    )
    assert result["ok"] is False
    assert result["error_class"] == "bad_params"
    assert result["correction"]
    assert "valid ids" in result["error"]
    assert call_tool("get_design_program", {"part": "brake_pedal"})["rev"] == rev0


def test_solve_follows_program_material(workspace, no_freecad):
    assert call_tool(
        "create_brake_pedal", {"material": "ti", "open_gui": False}
    )["ok"]
    result = call_tool("apply_load_and_solve", {"open_gui": False})
    assert result["ok"] is True
    assert result["material_id"] == "ti6al4v"
    assert result["yield_mpa"] == 880.0
    assert result["safety_factor_vs_yield"] == pytest.approx(
        880.0 / result["max_von_mises_mpa"], abs=0.01
    )
    al = bp.fallback_fea_result("xtruss", bp.DEFAULT_FORCE_N)
    assert result["pad_deflection_mm"] == pytest.approx(
        al["pad_deflection_mm"] * 69000.0 / 113800.0, rel=1e-3
    )


def test_compare_materials_from_session(workspace, no_freecad):
    assert call_tool("create_brake_pedal", {"open_gui": False})["ok"]
    assert call_tool("apply_load_and_solve", {"open_gui": False})["ok"]
    result = call_tool("compare_materials", {})
    assert result["ok"] is True
    assert result["base"]["source"] == "session"
    assert result["base"]["material"] == "Al 6061-T6"
    assert {row["material_id"] for row in result["rows"]} == EXPECTED_IDS
    by_id = {row["material_id"]: row for row in result["rows"]}
    assert by_id["pa12"]["deflection_not_verified"] is True
    assert by_id["ti6al4v"]["method"] == "precomputed_demo_estimate_scaled"
    # Ranking: lightest material whose SF still clears 1.5.
    assert result["recommendation"]["material_id"] == "pa12"
    assert result["recommendation"]["mass_kg"] == min(
        r["mass_kg"] for r in result["rows"]
    )
    # Citations present for every material.
    joined = "\n".join(result["citations"])
    for marker in ("6061-T6", "7075-T6", "Ti-6Al-4V", "PA12", "Steel-Generic"):
        assert marker in joined


def test_compare_materials_refuses_cold_cantilever(workspace, no_freecad):
    result = call_tool("compare_materials", {"part": "cantilever"})
    assert result["ok"] is False
    assert result["error_class"] == "no_results"
    assert "apply_load_and_solve" in result["correction"]


def test_cantilever_analytical_uses_material_modulus():
    al = cad_fea.analytical_cantilever_stress(100, 20, 5, 100, mats.get_material("al"))
    ti = cad_fea.analytical_cantilever_stress(100, 20, 5, 100, mats.get_material("ti"))
    # Same stress (geometry-driven); Ti deflection smaller by E_al/E_ti.
    assert al["max_von_mises_mpa"] == ti["max_von_mises_mpa"]
    assert ti["tip_deflection_mm"] == pytest.approx(
        al["tip_deflection_mm"] * 69000.0 / 113800.0, rel=1e-4
    )
    assert ti["material_id"] == "ti6al4v"


def test_cantilever_create_and_program_material(workspace, no_freecad):
    result = call_tool(
        "create_cantilever", {"material": "7075", "open_gui": False}
    )
    assert result["ok"] is True
    assert result["material_id"] == "al7075t6"
    program = call_tool("get_design_program", {"part": "cantilever"})
    assert program["params"]["material"] == "al7075t6"
    # material is no longer a fixed constant; defaults keep behavior identical
    assert "material" not in program["fixed"]


def test_compare_variants_uses_program_material_yield(workspace, no_freecad):
    assert call_tool("create_brake_pedal", {"material": "ti", "open_gui": False})["ok"]
    result = call_tool("compare_brake_pedal_variants", {})
    assert result["ok"] is True
    assert result["yield_mpa"] == 880.0
    assert "Ti-6Al-4V" in result["note"]
    for row in result["variants"]:
        vm = row["max_von_mises_mpa"]
        assert row["safety_factor_vs_yield"] == pytest.approx(880.0 / vm, abs=0.01)


def test_legacy_program_self_heals_material(workspace, no_freecad, monkeypatch):
    """Pre-F09 program files predate the material param; an edit re-commits
    them with their implicit default material."""
    import json

    program_path = workspace / "brake_pedal_program.json"
    legacy = {
        "part": "brake_pedal",
        "rev": 3,
        "params_hash": "deadbeefdead",
        "params": {"web_type": "xtruss", "cell_size_mm": 15.0, "strut_radius_mm": 2.5},
        "fixed": {},
    }
    program_path.write_text(json.dumps(legacy), encoding="utf-8")
    result = call_tool(
        "update_design_program",
        {"part": "brake_pedal", "changes": {"cell_size_mm": 12}, "open_gui": False},
    )
    assert result["ok"] is True
    program = call_tool("get_design_program", {"part": "brake_pedal"})
    assert program["params"]["material"] == "al6061t6"
    assert program["params"]["cell_size_mm"] == 12.0
    assert program["rev"] == 4
