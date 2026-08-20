"""F06 run history: append-only JSONL records + query_results tool.

All tests are memory-only (zero FreeCAD): solve paths are exercised through
the precomputed-fallback branch with `find_freecad_cmd` monkeypatched away.
"""

from __future__ import annotations

import json
import re

import pytest

from companion.config import get_settings
from companion.tools import cad_fea
from companion.tools import run_history as rh
from companion.tools.cad_fea import call_tool, reset_cad_sessions

RUN_ID_RE = re.compile(r"^\d{8}T\d{6}_[0-9a-f]{6}$")


def setup_function() -> None:
    reset_cad_sessions()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Isolate run history + program files in a tmp workspace."""
    settings = get_settings()
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    return tmp_path


def fake_result(force_n: float = 500.0, **extra) -> dict:
    result = {
        "ok": True,
        "part": "brake_pedal",
        "web_type": "xtruss",
        "method": "calculix_ccx",
        "force_n": force_n,
        "mesh_max_size_mm": 5.0,
        "node_count": 4053,
        "max_von_mises_mpa": 23.63,
        "max_vm_location_mm": [12.3, 45.6, 7.5],
        "pad_deflection_mm": 0.177,
        "mass_kg": 0.2536,
        "safety_factor_vs_yield": 11.68,
        "expected_vs_actual": {
            "expected_mpa": 45.06,
            "ratio": 0.524,
            "divergence_flag": False,
        },
        "fcstd_path": "data/workspace/brake_pedal_xtruss_fem.FCStd",
    }
    result.update(extra)
    return result


FAKE_GEOMETRY = {
    "part": "brake_pedal",
    "web_type": "xtruss",
    "cell_size_mm": 15.0,
    "strut_radius_mm": 2.5,
}


# --- record / read / find (pure module) ---


def test_record_run_stamps_result_and_appends(workspace):
    result = fake_result()
    run_id = rh.record_run(result, FAKE_GEOMETRY)
    assert run_id and RUN_ID_RE.match(run_id)
    assert result["run_id"] == run_id
    assert result["runs_path"].endswith("brake_pedal_runs.jsonl")
    runs = rh.read_runs("brake_pedal")
    assert len(runs) == 1
    record = runs[0]
    assert record["run_id"] == run_id
    assert record["method"] == "calculix_ccx"
    assert record["max_vm_location_mm"] == [12.3, 45.6, 7.5]
    assert record["cell_size_mm"] == 15.0
    assert record["expected_mpa"] == 45.06
    assert record["divergence_flag"] is False


def test_record_run_skips_failures_and_degrades_on_oserror(workspace, monkeypatch):
    assert rh.record_run({"ok": False}, FAKE_GEOMETRY) is None

    def boom(part: str):
        raise OSError("disk full")

    monkeypatch.setattr(rh, "runs_path", boom)
    result = fake_result()
    assert rh.record_run(result, FAKE_GEOMETRY) is None
    assert "history_write_error" in result  # warning key, never an exception


def test_read_runs_tails_and_skips_corrupt_lines(workspace):
    path = workspace / "brake_pedal_runs.jsonl"
    lines = [
        json.dumps({"run_id": "a", "force_n": 1}),
        "{not json",
        json.dumps({"run_id": "b", "force_n": 2}),
        json.dumps({"run_id": "c", "force_n": 3}),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    runs = rh.read_runs("brake_pedal", last_n=2)
    assert [run["run_id"] for run in runs] == ["b", "c"]


def test_find_run_searches_all_parts(workspace):
    pedal_id = rh.record_run(fake_result(), FAKE_GEOMETRY)
    cant_id = rh.record_run(
        fake_result(part="cantilever", max_von_mises_mpa=120.0),
        {"part": "cantilever", "length_mm": 100.0, "width_mm": 20.0, "height_mm": 5.0},
    )
    assert rh.find_run(pedal_id)["part"] == "brake_pedal"
    assert rh.find_run(cant_id)["part"] == "cantilever"  # found without part hint
    assert rh.find_run("20990101T000000_nope") is None


# --- query_results tool (through the outcome envelope) ---


def seed_active_pedal() -> None:
    cad_fea._session()["geometry"] = dict(FAKE_GEOMETRY)


def test_query_results_unknown_part_is_bad_params(workspace):
    out = call_tool("query_results", {"part": "warp_drive"})
    assert out["ok"] is False
    assert out["error_class"] == "bad_params"
    assert out["correction"]
    assert out["receipt"]["tool"] == "query_results"


def test_query_results_unknown_run_id_is_no_results(workspace):
    out = call_tool("query_results", {"run_id": "20990101T000000_nope"})
    assert out["ok"] is False
    assert out["error_class"] == "no_results"
    assert out["correction"]


def test_query_results_no_active_part_is_no_results(workspace):
    out = call_tool("query_results", {})
    assert out["ok"] is False
    assert out["error_class"] == "no_results"


def test_query_results_latest_then_by_run_id(workspace):
    first = rh.record_run(fake_result(force_n=500.0), FAKE_GEOMETRY)
    rh.record_run(fake_result(force_n=600.0, max_von_mises_mpa=28.0), FAKE_GEOMETRY)
    seed_active_pedal()

    out = call_tool("query_results", {})
    assert out["ok"] is True
    assert out["part"] == "brake_pedal"
    assert out["latest"]["force_n"] == 600.0
    assert out["max_vm_location_mm"] == [12.3, 45.6, 7.5]
    assert out["run_count"] == 2
    assert out["runs"][0]["force_n"] == 600.0  # newest first
    assert out["runs"][1]["force_n"] == 500.0
    assert "not captured" in out["reactions"]

    by_id = call_tool("query_results", {"run_id": first})
    assert by_id["ok"] is True
    assert by_id["run"]["force_n"] == 500.0


def test_query_results_part_with_no_runs(workspace):
    seed_active_pedal()
    out = call_tool("query_results", {"part": "cantilever"})
    assert out["ok"] is False
    assert out["error_class"] == "no_results"
    assert "cantilever" in out["correction"]


# --- solve-path integration (fallback branch, zero FreeCAD) ---


def test_solve_records_run_and_estimate(workspace, monkeypatch):
    monkeypatch.setattr(cad_fea, "find_freecad_cmd", lambda: None)
    created = call_tool("create_brake_pedal", {"web_type": "xtruss", "open_gui": False})
    assert created["ok"] is True

    solved = call_tool("apply_load_and_solve", {"open_gui": False})
    assert solved["ok"] is True
    assert RUN_ID_RE.match(solved["run_id"])
    eva = solved["expected_vs_actual"]
    assert eva["expected_mpa"] == pytest.approx(45.06, abs=0.2)
    assert eva["actual_mpa"] == pytest.approx(23.63, abs=0.1)  # precomputed xtruss
    assert eva["ratio"] == pytest.approx(0.524, abs=0.02)
    assert eva["divergence_flag"] is False
    assert "caveat" in eva  # xtruss compares against the solid-section estimate

    runs = rh.read_runs("brake_pedal")
    assert len(runs) == 1
    record = runs[-1]
    assert record["run_id"] == solved["run_id"]
    assert record["program_rev"] == 1  # seeded by the create above
    assert record["expected_mpa"] == eva["expected_mpa"]

    queried = call_tool("query_results", {})
    assert queried["ok"] is True
    assert queried["latest"]["run_id"] == solved["run_id"]
