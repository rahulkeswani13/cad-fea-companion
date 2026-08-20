"""F04 design program layer: specs, preflight, program IO, update transaction.

All tests are memory-only (zero FreeCAD): rebuilds are exercised through a
stubbed `create_brake_pedal`, and the real create-seeding path runs with
`find_freecad_cmd` monkeypatched to None (memory-geometry fallback).
"""

from __future__ import annotations

import json
import math

import pytest

from companion.config import get_settings
from companion.tools import design_program as dp
from companion.tools import cad_fea
from companion.tools.cad_fea import call_tool, reset_cad_sessions


def setup_function() -> None:
    reset_cad_sessions()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Isolate program files in a tmp workspace (programs are runtime state)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    return tmp_path


@pytest.fixture
def stub_pedal(monkeypatch):
    """Replace the brake-pedal rebuild path; record the params it was called
    with. Set `.fail_with` to make the rebuild fail."""
    calls: list[dict] = []
    holder = {"fail_with": None}

    def _fake_create(web_type="xtruss", cell_size_mm=15.0, strut_radius_mm=2.5, open_gui=True, material="al6061t6"):
        calls.append(
            {
                "web_type": web_type,
                "cell_size_mm": cell_size_mm,
                "strut_radius_mm": strut_radius_mm,
                "material": material,
            }
        )
        if holder["fail_with"] is not None:
            return dict(holder["fail_with"])
        return {
            "ok": True,
            "part": "brake_pedal",
            "web_type": web_type,
            "cell_size_mm": cell_size_mm,
            "strut_radius_mm": strut_radius_mm,
        }

    monkeypatch.setattr(cad_fea, "create_brake_pedal", _fake_create)
    holder["calls"] = calls
    return holder


def seed_pedal_program() -> dict:
    return dp.save_program("brake_pedal", dp.default_params("brake_pedal"), None)


# --- specs / hash / preflight / normalize (pure) ---


def test_defaults_are_in_range_for_every_part():
    for part in dp.KNOWN_PARTS:
        assert dp.editable_params(part)
        # F09: material is an editable enum param on every part; the
        # cantilever's fixed constants emptied when material left them (ADR-010).
        assert "material" in dp.editable_params(part)
        assert part in dp.FIXED_CONSTANTS
        assert dp.preflight(part, dp.default_params(part)) is None


def test_params_hash_is_canonical():
    h1 = dp.params_hash(
        {"web_type": "xtruss", "cell_size_mm": 12.0, "strut_radius_mm": 2.5}
    )
    h2 = dp.params_hash(
        {"strut_radius_mm": 2.5, "cell_size_mm": 12, "web_type": "xtruss"}
    )
    assert h1 == h2 and len(h1) == 12
    assert (
        dp.params_hash(
            {"web_type": "xtruss", "cell_size_mm": 13.0, "strut_radius_mm": 2.5}
        )
        != h1
    )


def test_preflight_rejects_out_of_range_with_named_range():
    failure = dp.preflight(
        "brake_pedal",
        {"web_type": "xtruss", "cell_size_mm": 0.5, "strut_radius_mm": 99.0},
    )
    assert failure is not None
    assert failure["error_class"] == "bad_params"
    assert "between 5.0 and 40.0" in failure["correction"]
    assert "between 1.0 and 5.0" in failure["correction"]
    assert set(failure["preflight"]["violations"]) == {
        "cell_size_mm",
        "strut_radius_mm",
    }


def test_preflight_rejects_nan():
    failure = dp.preflight(
        "brake_pedal",
        {"web_type": "xtruss", "cell_size_mm": math.nan, "strut_radius_mm": 2.5},
    )
    assert failure is not None
    assert failure["error_class"] == "bad_params"


def test_normalize_changes_aliases_coerces_and_rejects():
    normalized, failure = dp.normalize_changes(
        "brake_pedal", {"web_type": "bcc", "cell_size_mm": "12"}
    )
    assert failure is None
    assert normalized == {"web_type": "xtruss", "cell_size_mm": 12.0}

    _, failure = dp.normalize_changes("brake_pedal", {"thickness_z_mm": 20.0})
    assert failure and "fixed constant" in failure["error"]
    assert failure["error_class"] == "bad_params"

    _, failure = dp.normalize_changes("brake_pedal", {"banana": 1})
    assert failure and "not an editable parameter" in failure["error"]


def test_save_load_roundtrip_and_rev_bump(workspace):
    first = dp.save_program("cantilever", dp.default_params("cantilever"), None)
    assert first["rev"] == 1
    assert first["params_hash"] == dp.params_hash(first["params"])
    # F09: cantilever material moved from fixed constants to editable param.
    assert first["params"]["material"] == "steel"
    assert first["fixed"] == {}

    second = dp.save_program(
        "cantilever", {"length_mm": 120.0, "width_mm": 20.0, "height_mm": 5.0}, first["rev"]
    )
    assert second["rev"] == 2

    loaded = dp.load_program("cantilever")
    assert loaded == second
    # Atomic write leaves no temp file behind.
    assert not (workspace / "cantilever_program.json.tmp").exists()


# --- create seeding (real create path, FreeCAD absent) ---


def test_create_seeds_program_with_memory_geometry(workspace, monkeypatch):
    monkeypatch.setattr(cad_fea, "find_freecad_cmd", lambda: None)
    result = cad_fea.create_brake_pedal(web_type="xtruss", open_gui=False)
    assert result["ok"] is True

    program = dp.load_program("brake_pedal")
    assert program is not None
    assert program["rev"] == 1
    assert program["params"] == dp.default_params("brake_pedal")
    assert result["program"]["params_hash"] == program["params_hash"]

    # A second successful create bumps the revision (creates always commit).
    cad_fea.create_brake_pedal(web_type="xtruss", open_gui=False)
    assert dp.load_program("brake_pedal")["rev"] == 2


def test_failed_create_does_not_touch_program(workspace, monkeypatch):
    monkeypatch.setattr(cad_fea, "find_freecad_cmd", lambda: None)
    seed = seed_pedal_program()
    # Range-invalid params fail the F03 host gate before any program write.
    result = cad_fea.create_brake_pedal(
        web_type="xtruss", strut_radius_mm=0, open_gui=False
    )
    assert result["ok"] is False
    assert dp.load_program("brake_pedal") == seed


# --- get_design_program ---


def test_get_lists_programs_when_nothing_active(workspace):
    result = cad_fea.get_design_program()
    assert result["ok"] is True
    assert result["programs"] == []

    dp.save_program("brake_pedal", dp.default_params("brake_pedal"), 3)
    result = cad_fea.get_design_program()
    assert result["ok"] is True
    assert result["programs"] == [
        {"part": "brake_pedal", "rev": 4, "params_hash": dp.params_hash(dp.default_params("brake_pedal"))}
    ]


def test_get_returns_active_part_program(workspace, monkeypatch):
    monkeypatch.setattr(cad_fea, "find_freecad_cmd", lambda: None)
    cad_fea.create_cantilever(length_mm=90.0, open_gui=False)
    result = cad_fea.get_design_program()
    assert result["ok"] is True
    assert result["part"] == "cantilever"
    assert result["params"]["length_mm"] == 90.0
    assert result["path"].endswith("cantilever_program.json")


def test_get_unknown_part_rejected(workspace):
    result = cad_fea.get_design_program(part="warp_drive")
    assert result["ok"] is False
    assert result["error_class"] == "bad_params"


# --- update_design_program transaction ---


def test_update_requires_program_or_active_part(workspace, stub_pedal):
    result = cad_fea.update_design_program(changes={"cell_size_mm": 12})
    assert result["ok"] is False
    assert result["error_class"] == "no_geometry"

    result = cad_fea.update_design_program(
        part="brake_pedal", changes={"cell_size_mm": 12}
    )
    assert result["ok"] is False
    assert result["error_class"] == "no_geometry"
    assert "create_brake_pedal first" in result["correction"]
    assert not stub_pedal["calls"]


def test_update_cell_size_rebuilds_without_recreate(workspace, stub_pedal):
    seed = seed_pedal_program()
    result = cad_fea.update_design_program(
        part="brake_pedal", changes={"cell_size_mm": 12}, open_gui=False
    )
    assert result["ok"] is True
    assert result["changed"] is True

    # Exactly one rebuild, with the merged params — not a from-scratch guess.
    assert stub_pedal["calls"] == [
        {
            "web_type": "xtruss",
            "cell_size_mm": 12.0,
            "strut_radius_mm": 2.5,
            "material": "al6061t6",
        }
    ]
    committed = dp.load_program("brake_pedal")
    assert committed["rev"] == seed["rev"] + 1
    assert committed["params"]["cell_size_mm"] == 12.0
    assert committed["params_hash"] == dp.params_hash(committed["params"])
    assert result["program"]["rev"] == committed["rev"]


def test_failed_rebuild_preserves_accepted_revision(workspace, stub_pedal):
    seed = seed_pedal_program()
    stub_pedal["fail_with"] = {
        "ok": False,
        "error": "geometry validation failed at stage brep_invalid (part=brake_pedal)",
        "error_class": "geometry_invalid",
    }
    result = cad_fea.update_design_program(
        part="brake_pedal", changes={"cell_size_mm": 12}, open_gui=False
    )
    assert result["ok"] is False
    assert result["error_class"] == "geometry_invalid"
    assert result["attempted_changes"] == {"cell_size_mm": 12.0}
    assert result["program_preserved"]["rev"] == seed["rev"]
    # The accepted revision is untouched on disk.
    assert dp.load_program("brake_pedal") == seed


def test_noop_update_skips_rebuild_and_write(workspace, stub_pedal):
    seed = seed_pedal_program()
    before = (workspace / "brake_pedal_program.json").read_text()

    result = cad_fea.update_design_program(
        part="brake_pedal",
        changes={"cell_size_mm": 15.0, "web_type": "xtruss"},
        open_gui=False,
    )
    assert result["ok"] is True
    assert result["changed"] is False
    assert result["rev"] == seed["rev"]
    assert not stub_pedal["calls"]
    assert (workspace / "brake_pedal_program.json").read_text() == before

    # Alias normalization collapses bcc -> xtruss into a no-op too.
    result = cad_fea.update_design_program(
        part="brake_pedal", changes={"web_type": "bcc"}, open_gui=False
    )
    assert result["ok"] is True
    assert result["changed"] is False
    assert not stub_pedal["calls"]


def test_dry_run_previews_without_committing(workspace, stub_pedal):
    seed = seed_pedal_program()
    merged = {**seed["params"], "cell_size_mm": 12.0}

    result = cad_fea.update_design_program(
        part="brake_pedal", changes={"cell_size_mm": 12}, dry_run=True
    )
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["proposed"]["params"] == merged
    assert result["proposed"]["params_hash"] == dp.params_hash(merged)
    assert result["proposed"]["rev"] == seed["rev"] + 1
    assert result["current"]["params_hash"] == seed["params_hash"]
    assert not stub_pedal["calls"]
    assert dp.load_program("brake_pedal") == seed


def test_out_of_range_update_never_rebuilds(workspace, stub_pedal):
    seed = seed_pedal_program()
    result = cad_fea.update_design_program(
        part="brake_pedal", changes={"cell_size_mm": 0.5}, open_gui=False
    )
    assert result["ok"] is False
    assert result["error_class"] == "bad_params"
    assert "between 5.0 and 40.0" in result["correction"]
    assert not stub_pedal["calls"]
    assert dp.load_program("brake_pedal") == seed


def test_update_rejects_non_dict_changes(workspace, stub_pedal):
    seed_pedal_program()
    result = cad_fea.update_design_program(
        part="brake_pedal", changes="cell size 12", open_gui=False
    )
    assert result["ok"] is False
    assert result["error_class"] == "bad_params"
    assert not stub_pedal["calls"]


def test_call_tool_envelopes_program_tools(workspace, stub_pedal):
    seed_pedal_program()
    result = call_tool(
        "update_design_program",
        {"part": "brake_pedal", "changes": {"cell_size_mm": 12}, "open_gui": False},
    )
    assert result["ok"] is True
    assert result["receipt"]["tool"] == "update_design_program"
    assert isinstance(result["receipt"]["elapsed_s"], float)
    assert result["program"]["rev"] == 2

    listing = call_tool("get_design_program", {})
    assert listing["ok"] is True
    assert listing["receipt"]["tool"] == "get_design_program"
    # Stubbed rebuild leaves no active session part -> inventory listing.
    assert listing["programs"][0]["part"] == "brake_pedal"
    assert listing["programs"][0]["rev"] == 2

    rejected = call_tool(
        "update_design_program",
        {"part": "brake_pedal", "changes": {"cell_size_mm": 99}},
    )
    assert rejected["ok"] is False
    assert rejected["error_class"] == "bad_params"
    assert rejected["correction"]
    assert rejected["receipt"]["tool"] == "update_design_program"
