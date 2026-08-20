"""F08 mesh convergence study: ladder, verdict, honest refusals.

All tests are memory-only (zero FreeCAD): eligibility is faked with
`find_freecad_cmd` patched, and sub-runs go through a scripted
`apply_load_and_solve` stub on the cad_fea module (the same seam the real
dispatcher uses).
"""

from __future__ import annotations

import pytest

from companion.config import get_settings
from companion.tools import cad_fea
from companion.tools import convergence as conv
from companion.tools.cad_fea import call_tool, reset_cad_sessions

FAKE_FREECAD = "/fake/bin/FreeCADCmd"


def setup_function() -> None:
    reset_cad_sessions()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Keep any envelope debug-log writes out of the real workspace."""
    settings = get_settings()
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    return tmp_path


def seed_pedal(web_type: str = "xtruss") -> None:
    cad_fea._session()["geometry"] = {
        "part": "brake_pedal",
        "web_type": web_type,
        "cell_size_mm": 15.0,
        "strut_radius_mm": 2.5,
    }


def seed_cantilever() -> None:
    cad_fea._session()["geometry"] = {
        "part": "cantilever",
        "length_mm": 100.0,
        "width_mm": 20.0,
        "height_mm": 5.0,
    }


def script_solves(
    monkeypatch,
    by_mesh: dict[float, dict],
    calls: list | None = None,
) -> list:
    """Patch cad_fea.apply_load_and_solve with per-mesh scripted results."""
    calls = calls if calls is not None else []

    def _solve(force_n=None, mesh_max_size_mm=None, open_gui=True):
        calls.append(
            {
                "force_n": force_n,
                "mesh_max_size_mm": mesh_max_size_mm,
                "open_gui": open_gui,
            }
        )
        result = dict(by_mesh[float(mesh_max_size_mm)])
        if force_n is not None:
            result["force_n"] = force_n
        return result

    monkeypatch.setattr(cad_fea, "apply_load_and_solve", _solve)
    return calls


def live_result(vm: float, run_id: str, node_count: int = 4000, **extra) -> dict:
    result = {
        "ok": True,
        "part": "brake_pedal",
        "web_type": "xtruss",
        "method": "calculix_ccx",
        "force_n": 500.0,
        "max_von_mises_mpa": vm,
        "node_count": node_count,
        "pad_deflection_mm": 0.18,
        "run_id": run_id,
    }
    result.update(extra)
    return result


# --- honest refusals (live-solves-only gate) ---


def test_no_geometry_refused(workspace):
    out = call_tool("run_convergence_study", {})
    assert out["ok"] is False
    assert out["error_class"] == "no_geometry"
    assert out["correction"]
    assert out["receipt"]["tool"] == "run_convergence_study"


def test_fcc_refused_as_unsupported_setup(workspace, monkeypatch):
    monkeypatch.setattr(conv, "find_freecad_cmd", lambda: FAKE_FREECAD)
    seed_pedal(web_type="fcc")
    out = conv.run_convergence_study()
    assert out["ok"] is False
    assert out["error_class"] == "unsupported_setup"
    assert "xtruss" in out["correction"] or "solid" in out["correction"]


def test_missing_freecad_refused(workspace, monkeypatch):
    monkeypatch.setattr(conv, "find_freecad_cmd", lambda: None)
    seed_pedal()
    out = conv.run_convergence_study()
    assert out["ok"] is False
    assert out["error_class"] == "freecad_missing"
    assert out["correction"]


# --- ladder + explicit mesh list ---


def test_mesh_ladder_default_multipliers():
    assert conv.mesh_ladder(5.0) == [5.0, 3.5, 2.5]
    assert conv.mesh_ladder(2.5) == [2.5, 1.75, 1.25]
    assert conv.mesh_ladder(1.0) == [1.0, 0.7, 0.5]


def test_explicit_mesh_list_normalized_and_validated(workspace, monkeypatch):
    monkeypatch.setattr(conv, "find_freecad_cmd", lambda: FAKE_FREECAD)
    seed_cantilever()
    calls = script_solves(
        monkeypatch,
        {
            6.0: live_result(118.0, "r6", part="cantilever"),
            4.0: live_result(120.0, "r4", part="cantilever"),
        },
    )
    out = conv.run_convergence_study(mesh_sizes_mm=[4.0, 6.0])  # unsorted input
    assert out["ok"] is True
    assert [c["mesh_max_size_mm"] for c in calls] == [6.0, 4.0]  # coarse -> fine
    assert [row["mesh_max_size_mm"] for row in out["runs"]] == [6.0, 4.0]

    for bad in ("4", [5.0], [5.0, 3.0, 2.0, 1.0, 0.5], [5.0, 0.0], [5.0, 5.0]):
        failed = conv.run_convergence_study(mesh_sizes_mm=bad)
        assert failed["ok"] is False, bad
        assert failed["error_class"] == "bad_params", bad


# --- verdict logic ---


def test_converged_series_recommends_coarsest_within_tolerance(
    workspace, monkeypatch
):
    monkeypatch.setattr(conv, "find_freecad_cmd", lambda: FAKE_FREECAD)
    seed_pedal()
    script_solves(
        monkeypatch,
        {
            5.0: live_result(100.0, "r5"),
            3.5: live_result(97.6, "r35"),
            2.5: live_result(97.5, "r25"),
        },
    )
    out = call_tool("run_convergence_study", {})
    assert out["ok"] is True
    assert out["converged"] is True
    assert out["recommended_mesh_max_size_mm"] == 5.0
    assert out["incomplete"] is False
    assert out["failed_meshes"] == []
    assert out["metric"] == "max_von_mises_mpa"
    assert out["tolerance_pct"] == 5.0
    assert [row["run_id"] for row in out["runs"]] == ["r5", "r35", "r25"]
    # pct change vs previous coarser run; coarsest row has none
    assert out["runs"][0]["pct_change_vs_coarser"] is None
    assert out["runs"][1]["pct_change_vs_coarser"] == pytest.approx(
        2.46, abs=0.01
    )
    assert out["receipt"]["tool"] == "run_convergence_study"
    assert "calculix_ccx" in out["note"] and "Not verified" in out["note"]


def test_not_converged_recommends_finest_with_refine_flag(workspace, monkeypatch):
    monkeypatch.setattr(conv, "find_freecad_cmd", lambda: FAKE_FREECAD)
    seed_pedal()
    script_solves(
        monkeypatch,
        {
            5.0: live_result(60.0, "r5"),
            3.5: live_result(80.0, "r35"),
            2.5: live_result(95.0, "r25"),
        },
    )
    out = conv.run_convergence_study()
    assert out["ok"] is True
    assert out["converged"] is False
    assert out["recommended_mesh_max_size_mm"] == 2.5  # best-available only
    assert "refine further" in out["verdict"]


# --- sub-run behavior + failure honesty ---


def test_sub_runs_are_headless_and_force_passes_through(workspace, monkeypatch):
    monkeypatch.setattr(conv, "find_freecad_cmd", lambda: FAKE_FREECAD)
    seed_pedal()
    calls = script_solves(
        monkeypatch,
        {
            5.0: live_result(100.0, "r5"),
            3.5: live_result(99.0, "r35"),
            2.5: live_result(98.5, "r25"),
        },
    )
    out = conv.run_convergence_study(force_n=600.0)
    assert len(calls) == 3
    assert all(call["open_gui"] is False for call in calls)
    assert all(call["force_n"] == 600.0 for call in calls)
    assert out["force_n"] == 600.0


def test_fallback_mid_study_marks_mesh_failed_and_incomplete(
    workspace, monkeypatch
):
    monkeypatch.setattr(conv, "find_freecad_cmd", lambda: FAKE_FREECAD)
    seed_pedal()
    script_solves(
        monkeypatch,
        {
            5.0: live_result(100.0, "r5"),
            3.5: live_result(97.6, "r35"),
            2.5: {
                "ok": True,
                "part": "brake_pedal",
                "web_type": "xtruss",
                "method": "precomputed_demo_estimate",
                "fallback": True,
                "force_n": 500.0,
                "max_von_mises_mpa": 23.63,
            },
        },
    )
    out = conv.run_convergence_study()
    assert out["ok"] is True
    assert out["incomplete"] is True
    assert len(out["failed_meshes"]) == 1
    assert out["failed_meshes"][0]["mesh_max_size_mm"] == 2.5
    assert "not a live CalculiX solve" in out["failed_meshes"][0]["error"]
    # Verdict still computed from the two completed live runs.
    assert out["converged"] is True
    assert out["recommended_mesh_max_size_mm"] == 5.0


def test_failed_mesh_reported_not_silent(workspace, monkeypatch):
    monkeypatch.setattr(conv, "find_freecad_cmd", lambda: FAKE_FREECAD)
    seed_pedal()
    script_solves(
        monkeypatch,
        {
            5.0: live_result(100.0, "r5"),
            3.5: {
                "ok": False,
                "error": (
                    "Traceback (most recent call last):\n  File x.py\n"
                    "RuntimeError: CalculiX solve failed, no von Mises results"
                ),
                "error_class": "solve_failed",
            },
            2.5: live_result(97.5, "r25"),
        },
    )
    out = conv.run_convergence_study()
    assert out["ok"] is True
    assert out["incomplete"] is True
    failed = out["failed_meshes"][0]
    assert failed["mesh_max_size_mm"] == 3.5
    assert failed["error_class"] == "solve_failed"
    assert "Traceback" not in failed["error"]  # condensed to one line
    assert [row["mesh_max_size_mm"] for row in out["runs"]] == [5.0, 2.5]


def test_single_success_gives_no_verdict(workspace, monkeypatch):
    monkeypatch.setattr(conv, "find_freecad_cmd", lambda: FAKE_FREECAD)
    seed_pedal()
    script_solves(
        monkeypatch,
        {
            6.0: live_result(100.0, "r6"),
            3.0: {"ok": False, "error": "Gmsh mesh failed", "error_class": "mesh_failed"},
        },
    )
    out = conv.run_convergence_study(mesh_sizes_mm=[6.0, 3.0])
    assert out["ok"] is True
    assert out["incomplete"] is True
    assert out["converged"] is None
    assert out["recommended_mesh_max_size_mm"] is None
    assert "fewer than two" in out["verdict"]


def test_all_meshes_fail_is_failure_envelope(workspace, monkeypatch):
    monkeypatch.setattr(conv, "find_freecad_cmd", lambda: FAKE_FREECAD)
    seed_pedal()
    script_solves(
        monkeypatch,
        {
            5.0: {"ok": False, "error": "Gmsh mesh failed", "error_class": "mesh_failed"},
            3.5: {"ok": False, "error": "CalculiX timed out", "error_class": "freecad_timeout"},
            2.5: {"ok": False, "error": "CalculiX timed out", "error_class": "freecad_timeout"},
        },
    )
    out = call_tool("run_convergence_study", {})
    assert out["ok"] is False
    assert out["error_class"] == "freecad_timeout"  # last failure's class
    assert out["correction"]
    assert out["receipt"]["tool"] == "run_convergence_study"


# --- heuristic router picks the new tool ---


def test_router_routes_convergence_phrases():
    from companion.agent.graph import _heuristic_tools

    for message in (
        "Is the mesh converged on the current part?",
        "Run a mesh convergence study",
        "Do a mesh sensitivity check please",
    ):
        names = [call["name"] for call in _heuristic_tools(message)]
        assert "run_convergence_study" in names, message
