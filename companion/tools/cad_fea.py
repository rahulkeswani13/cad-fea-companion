"""CAD/FEA tools: cantilever + brake-pedal lattice creation and coarse static analysis."""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

from companion.config import get_settings
from companion.tools import brake_pedal as bp
from companion.tools import design_program as dp
from companion.tools import estimate
from companion.tools import materials as mats
from companion.tools import outcome
from companion.tools import run_history as rh
from companion.tools import uav_arm as ua
from companion.tools.validate import validate_geometry_payload
from companion.tools.freecad_runtime import (
    find_freecad_cmd,
    open_in_freecad_gui,
    run_freecad_python,
)

_current_thread_id: ContextVar[str] = ContextVar("cad_fea_thread_id", default="default")
_SESSIONS: dict[str, dict[str, Any]] = {}


def cad_thread_id() -> str:
    return _current_thread_id.get() or "default"


@contextmanager
def cad_thread_scope(thread_id: str | None) -> Iterator[str]:
    """Bind CAD session state to a chat thread for the current call stack."""
    tid = thread_id or "default"
    token = _current_thread_id.set(tid)
    try:
        yield tid
    finally:
        try:
            _current_thread_id.reset(token)
        except ValueError:
            pass


def _blank_session() -> dict[str, Any]:
    return {"geometry": None, "results": None}


def _session() -> dict[str, Any]:
    tid = cad_thread_id()
    sess = _SESSIONS.get(tid)
    if sess is None:
        sess = _blank_session()
        _SESSIONS[tid] = sess
    return sess


class _StateProxy:
    """Back-compat view of the current thread's CAD session."""

    def __getitem__(self, key: str) -> Any:
        return _session()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        _session()[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return _session().get(key, default)


_STATE = _StateProxy()


def get_state() -> dict[str, Any]:
    return dict(_session())


def reset_cad_sessions() -> None:
    _SESSIONS.clear()


def _write_runtime_results(filename: str, payload: dict[str, Any]) -> str:
    """Persist the latest solve under workspace/, never golden data/results/ files."""
    settings = get_settings()
    settings.ensure_dirs()
    path = settings.workspace_dir / filename
    to_store = {k: v for k, v in payload.items() if k != "gui"}
    path.write_text(json.dumps(to_store, indent=2, default=str), encoding="utf-8")
    return str(path)


def _record_program(part: str, result: dict[str, Any], params: dict[str, Any]) -> None:
    """F04: every successful create commits the design program (bump rev).

    Additive bookkeeping — a failed program write must never fail an otherwise
    successful geometry create, so OSError degrades to a warning key.
    """
    try:
        prev = dp.load_program(part)
        program = dp.save_program(part, params, (prev or {}).get("rev"))
        result["program"] = {
            "part": part,
            "rev": program["rev"],
            "params_hash": program["params_hash"],
        }
    except OSError as exc:
        result["program_write_error"] = str(exc)


def _record_solve(result: dict[str, Any], geometry: dict[str, Any] | None) -> None:
    """F06/F07 bookkeeping on a successful solve: attach the expected-vs-actual
    analytical estimate, then append a run-history record.

    Additive and best-effort — bookkeeping failures degrade to warning keys
    and must never fail an otherwise successful solve (mirrors
    ``_record_program``).
    """
    try:
        part = str(result.get("part") or (geometry or {}).get("part") or "").strip()
        force = result.get("force_n")
        eva = estimate.expected_vs_actual(
            part, geometry, float(force or 0.0), result.get("max_von_mises_mpa")
        )
        if eva:
            result["expected_vs_actual"] = eva
    except Exception as exc:  # noqa: BLE001 — estimate must not fail the solve
        result["estimate_error"] = f"{type(exc).__name__}: {exc}"
    try:
        rh.record_run(result, geometry)
    except Exception as exc:  # noqa: BLE001 — history must not fail the solve
        result["history_write_error"] = f"{type(exc).__name__}: {exc}"


def _scale_precomputed_force(data: dict[str, Any], force_n: float) -> dict[str, Any]:
    stored_f = float(data.get("stored_force_n") or data.get("force_n") or force_n)
    data["ok"] = True
    data["fallback"] = True
    if stored_f and abs(stored_f - force_n) > 1e-6:
        scale = force_n / stored_f
        if data.get("max_von_mises_mpa") is not None:
            data["max_von_mises_mpa"] = round(float(data["max_von_mises_mpa"]) * scale, 4)
        for key in ("pad_deflection_mm", "tip_deflection_mm"):
            if data.get(key) is not None:
                data[key] = round(float(data[key]) * scale, 6)
    data["force_n"] = force_n
    return data


def analytical_cantilever_stress(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    force_n: float,
    material: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Euler-Bernoulli cantilever with tip load (bending about weak axis height).

    Beam along X, cross-section width (Y) x height (Z), load in -Z.
    sigma_max = 6*F*L / (b * h^2)  [N/mm^2 = MPa]
    delta_max = F*L^3 / (3*E*I)
    """
    length_m = length_mm / 1000.0
    width_m = width_mm / 1000.0
    height_m = height_mm / 1000.0
    if material:
        e_pa = float(material["youngs_modulus_mpa"]) * 1e6
        mat_desc = mats.describe(material)
        mat_id = str(material["id"])
    else:
        e_pa = 210e9  # steel
        mat_desc = "Steel approx E=210 GPa, nu=0.3"
        mat_id = "steel"
    i = width_m * height_m**3 / 12.0
    sigma_mpa = (6.0 * force_n * length_mm) / (width_mm * height_mm**2)
    tip_defl_mm = (force_n * length_m**3 / (3.0 * e_pa * i)) * 1000.0
    return {
        "ok": True,
        "method": "analytical_euler_bernoulli",
        "material": mat_desc,
        "material_id": mat_id,
        "length_mm": length_mm,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "force_n": force_n,
        "max_von_mises_mpa": round(sigma_mpa, 4),
        "max_bending_stress_mpa": round(sigma_mpa, 4),
        "tip_deflection_mm": round(tip_defl_mm, 6),
        "notes": (
            "Closed-form verification reference. Coarse tet meshes under-predict "
            "peak bending stress relative to this value."
        ),
    }


def create_cantilever(
    length_mm: float = 100.0,
    width_mm: float = 20.0,
    height_mm: float = 5.0,
    open_gui: bool = False,
    material: str = mats.DEFAULT_PART_MATERIAL["cantilever"],
) -> dict[str, Any]:
    """Create a rectangular cantilever solid with FreeCAD and export STEP/STL."""
    mat = mats.get_material(material)
    if mat is None:
        return mats.bad_material_payload(material, "for cantilever")
    gate = validate_geometry_payload(
        {"length_mm": length_mm, "width_mm": width_mm, "height_mm": height_mm}
    )
    if gate:
        return gate
    settings = get_settings()
    settings.ensure_dirs()
    out_step = settings.exports_dir / "cantilever.step"
    out_stl = settings.exports_dir / "cantilever.stl"
    out_fcstd = settings.workspace_dir / "cantilever.FCStd"
    mat_name = mat["display_name"]
    mat_e = float(mat["youngs_modulus_mpa"])
    mat_nu = float(mat["poissons_ratio"])
    mat_density = float(mat["density_kg_m3"])
    mat_desc = mats.describe(mat)

    script = f"""
import json
import traceback
import FreeCAD as App
import Part

try:
    doc = App.newDocument("Cantilever")
    length = float({length_mm})
    width = float({width_mm})
    height = float({height_mm})
    # Part::Box keeps Face1=root (x=0) / Face2=tip like FreeCAD FEM examples.
    obj = doc.addObject("Part::Box", "CantileverBeam")
    obj.Length = length
    obj.Width = width
    obj.Height = height
    doc.recompute()

    step_path = r"{out_step}"
    stl_path = r"{out_stl}"
    fcstd_path = r"{out_fcstd}"
    Part.export([obj], step_path)
    obj.Shape.exportStl(stl_path)
    for o in doc.Objects:
        try:
            o.Visibility = True
        except Exception:
            pass
    doc.saveAs(fcstd_path)

    payload = {{
        "ok": True,
        "part": "cantilever",
        "name": "CantileverBeam",
        "length_mm": length,
        "width_mm": width,
        "height_mm": height,
        "volume_mm3": obj.Shape.Volume,
        "material": "{mat_desc}",
        "material_id": "{mat['id']}",
        "yield_mpa": {float(mat['yield_mpa'])},
        "step_path": step_path,
        "stl_path": stl_path,
        "fcstd_path": fcstd_path,
        "fixed_face": "Face1 (x=0 root)",
        "load_face": "Face2 (x=L tip)",
    }}
except Exception:
    payload = {{"ok": False, "error": traceback.format_exc()}}
print("COMPANION_JSON:" + json.dumps(payload))
"""

    def _memory_geometry(warning: str) -> dict[str, Any]:
        return {
            "ok": True,
            "part": "cantilever",
            "name": "CantileverBeam",
            "length_mm": length_mm,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "volume_mm3": length_mm * width_mm * height_mm,
            "material": mat_desc,
            "material_id": mat["id"],
            "yield_mpa": float(mat["yield_mpa"]),
            "step_path": None,
            "stl_path": None,
            "fcstd_path": None,
            "fixed_face": "Face1 (x=0 root)",
            "load_face": "Face2 (x=L tip)",
            "warning": warning,
        }

    if not find_freecad_cmd():
        result = _memory_geometry(
            "FreeCAD not installed; geometry recorded in memory only."
        )
    else:
        result = run_freecad_python(script)
        if not result.get("ok"):
            freecad_error = result.get("error", "unknown")
            result = _memory_geometry(
                f"FreeCADCmd failed ({freecad_error}); "
                "geometry recorded in memory only."
            )
            result["freecad_error"] = freecad_error

    if result.get("ok"):
        _STATE["geometry"] = result
        _STATE["results"] = None
        _record_program(
            "cantilever",
            result,
            {
                "length_mm": length_mm,
                "width_mm": width_mm,
                "height_mm": height_mm,
                "material": mat["id"],
            },
        )
        if open_gui and result.get("fcstd_path"):
            gui = open_in_freecad_gui(result["fcstd_path"])
            result["gui"] = gui
    return result


def create_brake_pedal(
    web_type: str = "xtruss",
    cell_size_mm: float = bp.DEFAULT_CELL_SIZE_MM,
    strut_radius_mm: float = bp.DEFAULT_STRUT_RADIUS_MM,
    open_gui: bool = False,
    material: str = mats.DEFAULT_PART_MATERIAL["brake_pedal"],
) -> dict[str, Any]:
    """Create brake-pedal bracket with solid or lattice web; export STEP/STL."""
    settings = get_settings()
    settings.ensure_dirs()
    mat = mats.get_material(material)
    if mat is None:
        return mats.bad_material_payload(material, "for brake_pedal")
    wt = bp.normalize_web_type(web_type)
    if wt not in bp.WEB_TYPES:
        return {
            "ok": False,
            "error": f"web_type must be one of {sorted(bp.WEB_TYPES)}, got {web_type!r}",
        }
    gate = validate_geometry_payload(
        {"cell_size_mm": cell_size_mm, "strut_radius_mm": strut_radius_mm}
    )
    if gate:
        return gate

    out_step = settings.exports_dir / f"brake_pedal_{wt}.step"
    out_stl = settings.exports_dir / f"brake_pedal_{wt}.stl"
    out_fcstd = settings.workspace_dir / f"brake_pedal_{wt}.FCStd"
    script = bp.build_geometry_script(
        wt,
        cell_size_mm,
        strut_radius_mm,
        str(out_step),
        str(out_stl),
        str(out_fcstd),
        material=mat,
    )

    if not find_freecad_cmd():
        result = bp.memory_geometry(
            wt,
            cell_size_mm,
            strut_radius_mm,
            "FreeCAD not installed; geometry recorded in memory only.",
            material=mat,
        )
    else:
        result = run_freecad_python(script, timeout=180)
        if not result.get("ok"):
            freecad_error = result.get("error", "unknown")
            result = bp.memory_geometry(
                wt,
                cell_size_mm,
                strut_radius_mm,
                f"FreeCADCmd failed ({freecad_error}); geometry recorded in memory only.",
                material=mat,
            )
            result["freecad_error"] = freecad_error

    if result.get("ok"):
        _STATE["geometry"] = result
        _STATE["results"] = None
        _record_program(
            "brake_pedal",
            result,
            {
                "web_type": wt,
                "cell_size_mm": cell_size_mm,
                "strut_radius_mm": strut_radius_mm,
                "material": mat["id"],
            },
        )
        if open_gui and result.get("fcstd_path"):
            result["gui"] = open_in_freecad_gui(result["fcstd_path"])
    return result


def _active_part() -> str | None:
    geometry = _STATE.get("geometry") or {}
    part = str(geometry.get("part") or "").strip()
    return part or None


def create_uav_arm(
    web_type: str = "solid",
    arm_length_mm: float = ua.ARM_LENGTH_MM,
    cell_size_mm: float = ua.DEFAULT_CELL_SIZE_MM,
    strut_radius_mm: float = ua.DEFAULT_STRUT_RADIUS_MM,
    open_gui: bool = False,
    material: str = mats.DEFAULT_PART_MATERIAL["uav_arm"],
) -> dict[str, Any]:
    """F26: create the UAV arm (boss + tapered arm + motor ring); export STEP/STL."""
    settings = get_settings()
    settings.ensure_dirs()
    mat = mats.get_material(material)
    if mat is None:
        return mats.bad_material_payload(material, "for uav_arm")
    wt = ua.normalize_web_type(web_type)
    if wt not in ua.WEB_TYPES:
        return {
            "ok": False,
            "error": f"web_type must be one of {sorted(ua.WEB_TYPES)}, got {web_type!r}",
            "error_class": "bad_params",
            "correction": "Use web_type='solid' or 'xtruss' ('x-truss'/'bcc' alias to xtruss).",
        }
    gate = validate_geometry_payload(
        {
            "arm_length_mm": arm_length_mm,
            "cell_size_mm": cell_size_mm,
            "strut_radius_mm": strut_radius_mm,
        }
    )
    if gate:
        return gate

    out_step = settings.exports_dir / f"uav_arm_{wt}.step"
    out_stl = settings.exports_dir / f"uav_arm_{wt}.stl"
    out_fcstd = settings.workspace_dir / f"uav_arm_{wt}.FCStd"
    script = ua.build_geometry_script(
        wt,
        float(arm_length_mm),
        str(out_step),
        str(out_stl),
        str(out_fcstd),
        material_id=str(mat["id"]),
        cell_size_mm=float(cell_size_mm),
        strut_radius_mm=float(strut_radius_mm),
    )

    if not find_freecad_cmd():
        result = ua.memory_geometry(
            wt,
            float(arm_length_mm),
            float(cell_size_mm),
            float(strut_radius_mm),
            "FreeCAD not installed; geometry recorded in memory only.",
            material_id=str(mat["id"]),
        )
    else:
        result = run_freecad_python(script, timeout=180)
        if not result.get("ok"):
            freecad_error = result.get("error", "unknown")
            result = ua.memory_geometry(
                wt,
                float(arm_length_mm),
                float(cell_size_mm),
                float(strut_radius_mm),
                f"FreeCADCmd failed ({freecad_error}); geometry recorded in memory only.",
                material_id=str(mat["id"]),
            )
            result["freecad_error"] = freecad_error

    if result.get("ok"):
        _STATE["geometry"] = result
        _STATE["results"] = None
        _record_program(
            "uav_arm",
            result,
            {
                "web_type": wt,
                "arm_length_mm": float(arm_length_mm),
                "cell_size_mm": float(cell_size_mm),
                "strut_radius_mm": float(strut_radius_mm),
                "material": str(mat["id"]),
            },
        )
        if open_gui and result.get("fcstd_path"):
            result["gui"] = open_in_freecad_gui(result["fcstd_path"])
    return result


def get_design_program(part: str | None = None) -> dict[str, Any]:
    """F04: persisted params + revision hash for a part (source of truth)."""
    settings = get_settings()
    settings.ensure_dirs()
    key = str(part or "").strip() or None
    if key and key not in dp.KNOWN_PARTS:
        return {
            "ok": False,
            "error": f"unknown part {part!r}; known parts: {list(dp.KNOWN_PARTS)}",
            "error_class": "bad_params",
            "correction": (
                "Use one of brake_pedal, cantilever, uav_arm "
                "(or omit part to use the active one)."
            ),
        }
    if not key:
        key = _active_part()
    if key:
        program = dp.load_program(key)
        if program is None:
            return {
                "ok": False,
                "error": f"No design program for {key} on disk yet.",
                "error_class": "no_geometry",
                "correction": f"Call create_{key} first to seed the program, then retry.",
            }
        return {"ok": True, **program, "path": str(dp.program_path(key))}
    programs = dp.list_programs()
    return {
        "ok": True,
        "programs": programs,
        "note": (
            "No active part this session. Create one (create_brake_pedal, "
            "create_uav_arm, or create_cantilever) or pass part= to read "
            "a specific program."
        ),
    }


def _rebuild_from_program(
    part: str, params: dict[str, Any], open_gui: bool
) -> dict[str, Any]:
    """Delegate the rebuild to the part's existing create path (F03 gate,
    FreeCAD dispatch, fallbacks, session update, and program commit all
    stay in one place)."""
    if part == "brake_pedal":
        return create_brake_pedal(
            web_type=str(params.get("web_type", "xtruss")),
            cell_size_mm=float(params.get("cell_size_mm", bp.DEFAULT_CELL_SIZE_MM)),
            strut_radius_mm=float(
                params.get("strut_radius_mm", bp.DEFAULT_STRUT_RADIUS_MM)
            ),
            open_gui=open_gui,
            material=str(
                params.get("material", mats.DEFAULT_PART_MATERIAL["brake_pedal"])
            ),
        )
    if part == "uav_arm":
        return create_uav_arm(
            web_type=str(params.get("web_type", "solid")),
            arm_length_mm=float(params.get("arm_length_mm", ua.ARM_LENGTH_MM)),
            cell_size_mm=float(params.get("cell_size_mm", ua.DEFAULT_CELL_SIZE_MM)),
            strut_radius_mm=float(
                params.get("strut_radius_mm", ua.DEFAULT_STRUT_RADIUS_MM)
            ),
            open_gui=open_gui,
            material=str(
                params.get("material", mats.DEFAULT_PART_MATERIAL["uav_arm"])
            ),
        )
    return create_cantilever(
        length_mm=float(params.get("length_mm", 100.0)),
        width_mm=float(params.get("width_mm", 20.0)),
        height_mm=float(params.get("height_mm", 5.0)),
        open_gui=open_gui,
        material=str(
            params.get("material", mats.DEFAULT_PART_MATERIAL["cantilever"])
        ),
    )


def update_design_program(
    part: str | None = None,
    changes: dict[str, Any] | None = None,
    dry_run: bool = False,
    open_gui: bool = False,
) -> dict[str, Any]:
    """F04: edit program params, preflight, rebuild, commit rev on success.

    "set cell size to 12" without recreating from scratch. Hard failures
    (bad params, validation gate, FreeCAD crash) leave the accepted revision
    untouched on disk; a no-op change rebuilds nothing and bumps nothing.
    """
    settings = get_settings()
    settings.ensure_dirs()
    key = str(part or "").strip() or None
    if key and key not in dp.KNOWN_PARTS:
        return {
            "ok": False,
            "error": f"unknown part {part!r}; known parts: {list(dp.KNOWN_PARTS)}",
            "error_class": "bad_params",
            "correction": "Use one of brake_pedal, cantilever, uav_arm.",
        }
    if not key:
        key = _active_part()
    if not key:
        return {
            "ok": False,
            "error": "No active part and no part given.",
            "error_class": "no_geometry",
            "correction": (
                "Call create_brake_pedal, create_uav_arm, or "
                "create_cantilever first, then retry the edit."
            ),
        }
    program = dp.load_program(key)
    if program is None:
        return {
            "ok": False,
            "error": f"No design program for {key} on disk yet.",
            "error_class": "no_geometry",
            "correction": f"Call create_{key} first to seed the program, then retry.",
        }
    if changes is not None and not isinstance(changes, dict):
        return {
            "ok": False,
            "error": (
                "changes must be an object mapping parameter names to values, "
                f"got {type(changes).__name__}"
            ),
            "error_class": "bad_params",
            "correction": 'Pass changes as an object, e.g. {"cell_size_mm": 12}.',
        }

    normalized, failure = dp.normalize_changes(key, changes or {})
    if failure:
        return failure
    merged = {**program.get("params", {}), **normalized}
    # Self-heal pre-F09 program files: they predate the material param, so a
    # legacy edit re-commits the program with its implicit default material.
    merged.setdefault(
        "material", mats.DEFAULT_PART_MATERIAL.get(key, "al6061t6")
    )
    failure = dp.preflight(key, merged)
    if failure:
        return failure

    new_hash = dp.params_hash(merged)
    current_rev = program.get("rev")
    current_hash = program.get("params_hash")
    if new_hash == current_hash:
        return {
            "ok": True,
            "changed": False,
            "part": key,
            "rev": current_rev,
            "params_hash": current_hash,
            "params": merged,
            "note": (
                "No parameter change after normalization; current design kept "
                "(no rebuild, no rev bump)."
            ),
        }
    if dry_run:
        return {
            "ok": True,
            "changed": True,
            "dry_run": True,
            "part": key,
            "current": {"rev": current_rev, "params_hash": current_hash},
            "proposed": {
                "params": merged,
                "params_hash": new_hash,
                "rev": int(current_rev or 0) + 1,
            },
            "note": "Preflight passed; dry_run set so nothing was rebuilt or committed.",
        }

    rebuilt = _rebuild_from_program(key, merged, open_gui)
    if not rebuilt.get("ok"):
        # Hard failure: disk keeps the accepted revision; echo what was tried.
        rebuilt.setdefault("attempted_changes", normalized)
        rebuilt["program_preserved"] = {
            "part": key,
            "rev": current_rev,
            "params_hash": current_hash,
        }
        return rebuilt

    rebuilt["changed"] = True
    # The create path commits the program itself; ensure-commit covers the
    # degraded case where that write failed (OSError) or a test stubbed it.
    committed = dp.load_program(key)
    if committed is None or committed.get("params_hash") != new_hash:
        try:
            committed = dp.save_program(key, merged, (committed or {}).get("rev"))
        except OSError as exc:
            rebuilt["program_write_error"] = str(exc)
    if committed and committed.get("params_hash") == new_hash:
        rebuilt["program"] = {
            "part": key,
            "rev": committed["rev"],
            "params_hash": committed["params_hash"],
        }
    return rebuilt


def get_lattice_metrics() -> dict[str, Any]:
    """Relative density, volumes, and mass for current lattice geometry (mount or pedal)."""
    geometry = _STATE.get("geometry")
    part = (geometry or {}).get("part")
    if not geometry or part != "brake_pedal":
        return {
            "ok": False,
            "error": (
                "No lattice geometry. Call create_brake_pedal first."
            ),
        }
    mod = bp
    vols = mod.estimate_part_volume_mm3(
        str(geometry.get("web_type", "xtruss")),
        float(geometry.get("cell_size_mm", mod.DEFAULT_CELL_SIZE_MM)),
        float(geometry.get("strut_radius_mm", mod.DEFAULT_STRUT_RADIUS_MM)),
    )
    # Prefer measured FreeCAD volumes when present.
    out = {
        "ok": True,
        "part": part,
        "web_type": geometry.get("web_type"),
        "cell_size_mm": geometry.get("cell_size_mm"),
        "strut_radius_mm": geometry.get("strut_radius_mm"),
        "nx": geometry.get("nx"),
        "ny": geometry.get("ny"),
        "nz": geometry.get("nz"),
        "material": geometry.get("material"),
        "yield_mpa": geometry.get(
            "yield_mpa", mats.material_for_part("brake_pedal")["yield_mpa"]
        ),
        **vols,
    }
    for key in (
        "volume_mm3",
        "lattice_fill_volume_mm3",
        "pocket_volume_mm3",
        "relative_density",
        "mass_kg",
        "skins_volume_mm3",
    ):
        if geometry.get(key) is not None:
            out[key] = geometry[key]
    if out.get("web_type") == "solid":
        out["relative_density"] = 1.0
    return out


def compare_brake_pedal_variants() -> dict[str, Any]:
    """Compare solid / X-truss / FCC brake-pedal KPIs from session or precomputed JSON."""
    settings = get_settings()
    settings.ensure_dirs()
    variants: list[dict[str, Any]] = []
    session = _STATE.get("results") or {}
    session_geo = _STATE.get("geometry") or {}
    # F09: SF is judged against the program material's yield (default Al).
    prog_mat = mats.resolve_result_material(session_geo, "brake_pedal")

    for wt in ("solid", "xtruss", "fcc"):
        row: dict[str, Any] | None = None
        if (
            session.get("part") == "brake_pedal"
            and session.get("web_type") == wt
            and session.get("max_von_mises_mpa") is not None
        ):
            row = {
                "web_type": wt,
                "source": "session",
                "mass_kg": session.get("mass_kg"),
                "relative_density": session.get("relative_density"),
                "max_von_mises_mpa": session.get("max_von_mises_mpa"),
                "pad_deflection_mm": session.get("pad_deflection_mm")
                or session.get("tip_deflection_mm"),
                "force_n": session.get("force_n"),
                "method": session.get("method"),
            }
        path = settings.results_dir / bp.precomputed_filename(wt)
        if row is None and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            row = {
                "web_type": wt,
                "source": "precomputed",
                "mass_kg": data.get("mass_kg"),
                "relative_density": data.get("relative_density"),
                "max_von_mises_mpa": data.get("max_von_mises_mpa"),
                "pad_deflection_mm": data.get("pad_deflection_mm")
                or data.get("tip_deflection_mm"),
                "force_n": data.get("force_n", bp.DEFAULT_FORCE_N),
                "method": data.get("method"),
            }
        if row is None:
            est = bp.fallback_fea_result(wt, bp.DEFAULT_FORCE_N)
            row = {
                "web_type": wt,
                "source": "estimate",
                "mass_kg": est.get("mass_kg"),
                "relative_density": est.get("relative_density"),
                "max_von_mises_mpa": est.get("max_von_mises_mpa"),
                "pad_deflection_mm": est.get("pad_deflection_mm"),
                "force_n": est.get("force_n"),
                "method": est.get("method"),
            }
        if row.get("mass_kg") is None or row.get("relative_density") is None:
            vols = bp.estimate_part_volume_mm3(wt)
            row.setdefault("mass_kg", vols["mass_kg"])
            row.setdefault("relative_density", vols["relative_density"])
        vm = row.get("max_von_mises_mpa")
        row["safety_factor_vs_yield"] = (
            round(float(prog_mat["yield_mpa"]) / float(vm), 3) if vm else None
        )
        variants.append(row)

    ok_sf = [v for v in variants if (v.get("safety_factor_vs_yield") or 0) >= 1.5]
    if ok_sf:
        recommendation = min(ok_sf, key=lambda v: float(v.get("mass_kg") or 1e9))
    else:
        recommendation = max(
            variants, key=lambda v: float(v.get("safety_factor_vs_yield") or 0)
        )

    return {
        "ok": True,
        "part": "brake_pedal",
        "material": prog_mat["display_name"],
        "yield_mpa": float(prog_mat["yield_mpa"]),
        "sf_threshold": 1.5,
        "variants": variants,
        "recommendation": recommendation,
        "session_web_type": session_geo.get("web_type"),
        "note": (
            "Compare mass, relative density, max von Mises, and pad deflection. "
            f"Recommend lowest mass with SF>=1.5 vs {prog_mat['display_name']} "
            f"yield (~{float(prog_mat['yield_mpa']):g} MPa)."
        ),
    }


def _cantilever_mass_kg(base: dict[str, Any], mat: dict[str, Any]) -> float | None:
    """L*b*h*rho when a stored cantilever run lacks a mass KPI."""
    try:
        vol_mm3 = float(base["length_mm"]) * float(base["width_mm"]) * float(base["height_mm"])
        return round(vol_mm3 * 1e-9 * float(mat["density_kg_m3"]), 6)
    except (KeyError, TypeError, ValueError):
        return None


def compare_materials(part: str | None = None) -> dict[str, Any]:
    """F09: compare the material table against the best available base run.

    Base-result ladder (always labeled): current session solve -> latest
    stored run (F06 history) -> committed precomputed KPIs -> demo estimate
    (brake pedal only; cantilever refuses instead of guessing). Every row is
    one material, scaled linear-elastically from the base material: stress
    unchanged, deflection x E_ref/E_new, mass x rho_new/rho_ref, SF vs that
    material's yield. Each row carries its citation sources; the PA12 row
    flags its deflection as not verified.
    """
    settings = get_settings()
    settings.ensure_dirs()
    key = str(part or "").strip() or None
    if key and key not in dp.KNOWN_PARTS:
        return {
            "ok": False,
            "error": f"unknown part {part!r}; known parts: {list(dp.KNOWN_PARTS)}",
            "error_class": "bad_params",
            "correction": "Use one of brake_pedal, cantilever, uav_arm.",
        }
    if not key:
        key = _active_part() or "brake_pedal"

    session = _STATE.get("results") or {}
    base: dict[str, Any] | None = None
    source = None
    if session.get("part") == key and session.get("max_von_mises_mpa") is not None:
        base, source = dict(session), "session"
    if base is None:
        try:
            runs = rh.read_runs(key, last_n=1)
        except OSError:
            runs = []
        if runs and runs[-1].get("max_von_mises_mpa") is not None:
            base, source = dict(runs[-1]), "run_history"
    if base is None:
        if key == "brake_pedal":
            geo = _STATE.get("geometry") or {}
            wt = bp.normalize_web_type(str(geo.get("web_type") or "xtruss"))
            path = settings.results_dir / bp.precomputed_filename(wt)
            if path.exists():
                base = json.loads(path.read_text(encoding="utf-8"))
                source = "precomputed"
        elif key == "uav_arm":
            geo = _STATE.get("geometry") or {}
            wt = ua.normalize_web_type(str(geo.get("web_type") or "solid"))
            path = settings.results_dir / ua.precomputed_filename(wt)
            if path.exists():
                base = json.loads(path.read_text(encoding="utf-8"))
                source = "precomputed"
        else:
            path = settings.results_dir / "cantilever_precomputed.json"
            if path.exists():
                base = json.loads(path.read_text(encoding="utf-8"))
                source = "precomputed"
    if base is None and key == "brake_pedal":
        geo = _STATE.get("geometry") or {}
        wt = bp.normalize_web_type(str(geo.get("web_type") or "xtruss"))
        base = bp.fallback_fea_result(wt, bp.DEFAULT_FORCE_N, geo)
        source = "estimate"
    if base is None and key == "uav_arm":
        geo = _STATE.get("geometry") or {}
        wt = ua.normalize_web_type(str(geo.get("web_type") or "solid"))
        base = ua.fallback_fea_result(wt, ua.DEFAULT_FORCE_N, geo)
        source = "estimate"
    if base is None:
        return {
            "ok": False,
            "error": f"No solved or stored results for {key} to compare materials against.",
            "error_class": "no_results",
            "correction": (
                f"Call apply_load_and_solve on {key} first (or create_{key} if no "
                "geometry exists), then retry compare_materials."
            ),
        }

    ref_mat = mats.resolve_result_material(base, key)
    if base.get("mass_kg") is None and key == "cantilever":
        mass = _cantilever_mass_kg(base, ref_mat)
        if mass is not None:
            base["mass_kg"] = mass

    rows: list[dict[str, Any]] = []
    for mat in mats.load_materials().values():
        scaled = mats.scale_result(base, mat, key)
        rows.append(
            {
                "material_id": mat["id"],
                "material": mat["display_name"],
                "family": mat["family"],
                "cost_class": mat["cost_class"],
                "mass_kg": scaled.get("mass_kg"),
                "max_von_mises_mpa": scaled.get("max_von_mises_mpa"),
                "safety_factor_vs_yield": scaled.get("safety_factor_vs_yield"),
                "deflection_mm": scaled.get("pad_deflection_mm")
                if scaled.get("pad_deflection_mm") is not None
                else scaled.get("tip_deflection_mm"),
                "method": scaled.get("method"),
                "deflection_not_verified": bool(
                    scaled.get("deflection_not_verified")
                ),
                "note": mat["note"],
                "sources": mat["sources"],
            }
        )

    ok_sf = [r for r in rows if (r.get("safety_factor_vs_yield") or 0) >= mats.SF_THRESHOLD]
    if ok_sf:
        recommendation = min(ok_sf, key=lambda r: float(r.get("mass_kg") or 1e9))
    else:
        recommendation = max(
            rows, key=lambda r: float(r.get("safety_factor_vs_yield") or 0)
        )

    return {
        "ok": True,
        "part": key,
        "sf_threshold": mats.SF_THRESHOLD,
        "base": {
            "source": source,
            "run_id": base.get("run_id"),
            "method": base.get("method"),
            "mesh_max_size_mm": base.get("mesh_max_size_mm"),
            "force_n": base.get("force_n"),
            "material": ref_mat["display_name"],
        },
        "rows": rows,
        "recommendation": recommendation,
        "citations": mats.citations_for(list(mats.load_materials().values())),
        "note": (
            "Linear-elastic scaling from the base run: stress assumed E-independent "
            "(approximate for the lattice), deflection x E ratio, mass x density "
            "ratio, SF vs each material's room-temperature yield. Not verified: "
            "fatigue, temperature effects, as-built AM lattice allowables, polymer "
            "large-deflection (see deflection_not_verified flags). Sources per row."
        ),
    }


def _apply_load_and_solve_brake_pedal(
    geometry: dict[str, Any],
    force_n: float,
    mesh_max_size_mm: float,
    open_gui: bool,
) -> dict[str, Any]:
    settings = get_settings()
    settings.ensure_dirs()
    web_type = bp.normalize_web_type(str(geometry.get("web_type", "xtruss")))
    cell_size_mm = float(geometry.get("cell_size_mm", bp.DEFAULT_CELL_SIZE_MM))
    strut_radius_mm = float(
        geometry.get("strut_radius_mm", bp.DEFAULT_STRUT_RADIUS_MM)
    )
    mat = mats.get_material(geometry.get("material_id")) or mats.material_for_part(
        "brake_pedal"
    )
    # FCC continuum needs thicker struts for a usable Gmsh volume mesh.
    if web_type == "fcc" and strut_radius_mm < 2.0:
        strut_radius_mm = 2.2
    gate = validate_geometry_payload(
        {"cell_size_mm": cell_size_mm, "strut_radius_mm": strut_radius_mm}
    )
    if gate:
        return gate
    precomputed_path = settings.results_dir / bp.precomputed_filename(web_type)
    out_fcstd = settings.workspace_dir / f"brake_pedal_{web_type}_fem.FCStd"

    def _load_precomputed_or_estimate(extra: dict[str, Any] | None = None) -> dict[str, Any]:
        if precomputed_path.exists():
            data = json.loads(precomputed_path.read_text(encoding="utf-8"))
            data = _scale_precomputed_force(data, force_n)
            # Committed precomputed KPIs are Al 6061-T6; re-express them in the
            # program material (linear-elastic scaling, honestly labeled).
            data = mats.scale_result(data, mat, "brake_pedal")
            if extra:
                data.update(extra)
                data["force_n"] = force_n
            return data
        return bp.fallback_fea_result(web_type, force_n, geometry, material=mat)

    fem_result: dict[str, Any] | None = None
    if web_type == "fcc":
        result = _load_precomputed_or_estimate(
            {"note": "FCC FEA uses precomputed/demo KPIs (no live continuum solve)."}
        )
    elif find_freecad_cmd():
        script = bp.build_fem_script(
            web_type,
            cell_size_mm,
            strut_radius_mm,
            force_n,
            mesh_max_size_mm,
            str(out_fcstd),
            material=mat,
        )
        fem_result = run_freecad_python(script, timeout=420)
        if fem_result and fem_result.get("ok"):
            result = fem_result
            result["stored_force_n"] = force_n
        elif settings.fem_allow_analytical_fallback:
            result = _load_precomputed_or_estimate(
                {
                    "freecad_error": (fem_result or {}).get("error"),
                }
            )
        else:
            return fem_result or {"ok": False, "error": "FEM failed and fallback disabled"}
    elif settings.fem_allow_analytical_fallback:
        result = _load_precomputed_or_estimate(
            {"warning": "FreeCAD not installed; using precomputed/estimate FEA."}
        )
    else:
        return {"ok": False, "error": "FreeCAD not installed and fallback disabled"}

    vm = result.get("max_von_mises_mpa")
    if vm:
        result["safety_factor_vs_yield"] = round(
            float(mat["yield_mpa"]) / float(vm), 3
        )
    result["ok"] = True
    result["part"] = "brake_pedal"
    result["web_type"] = web_type
    result["force_n"] = force_n
    result["mesh_max_size_mm"] = mesh_max_size_mm
    result.setdefault("material", mats.describe(mat))
    result.setdefault("material_id", mat["id"])
    result.setdefault("yield_mpa", float(mat["yield_mpa"]))

    _STATE["results"] = result
    if result.get("fcstd_path"):
        _STATE["geometry"] = {**(geometry or {}), "fcstd_path": result["fcstd_path"]}

    if open_gui:
        gui_path = None
        if result.get("method") == "calculix_ccx" and result.get("fcstd_path"):
            gui_path = result["fcstd_path"]
        elif result.get("fcstd_path") and not result.get("fallback"):
            gui_path = result["fcstd_path"]
        if gui_path:
            result["gui"] = open_in_freecad_gui(gui_path)
        elif result.get("fallback"):
            result["gui"] = {
                "ok": False,
                "skipped": True,
                "reason": (
                    "FEA fell back to precomputed KPIs (no stress pipeline to show). "
                    "Retry solve; xtruss uses 2.5 mm strut thickness and ~5 mm mesh."
                ),
            }

    _record_solve(result, geometry)
    result["results_path"] = _write_runtime_results(
        bp.precomputed_filename(web_type), result
    )
    return result


def _apply_load_and_solve_uav_arm(
    geometry: dict[str, Any],
    force_n: float,
    mesh_max_size_mm: float,
    open_gui: bool,
) -> dict[str, Any]:
    settings = get_settings()
    settings.ensure_dirs()
    web_type = ua.normalize_web_type(str(geometry.get("web_type", "solid")))
    arm_length_mm = float(geometry.get("arm_length_mm", ua.ARM_LENGTH_MM))
    cell_size_mm = float(geometry.get("cell_size_mm", ua.DEFAULT_CELL_SIZE_MM))
    strut_radius_mm = float(
        geometry.get("strut_radius_mm", ua.DEFAULT_STRUT_RADIUS_MM)
    )
    mat = mats.get_material(geometry.get("material_id")) or mats.material_for_part(
        "uav_arm"
    )
    gate = validate_geometry_payload(
        {
            "arm_length_mm": arm_length_mm,
            "cell_size_mm": cell_size_mm,
            "strut_radius_mm": strut_radius_mm,
        }
    )
    if gate:
        return gate
    precomputed_path = settings.results_dir / ua.precomputed_filename(web_type)
    out_fcstd = settings.workspace_dir / f"uav_arm_{web_type}_fem.FCStd"

    def _load_precomputed_or_estimate(extra: dict[str, Any] | None = None) -> dict[str, Any]:
        if precomputed_path.exists():
            data = json.loads(precomputed_path.read_text(encoding="utf-8"))
            data = _scale_precomputed_force(data, force_n)
            data = mats.scale_result(data, mat, "uav_arm")
            if extra:
                data.update(extra)
                data["force_n"] = force_n
            return data
        return ua.fallback_fea_result(
            web_type, force_n, geometry, material_id=str(mat["id"])
        )

    fem_result: dict[str, Any] | None = None
    if find_freecad_cmd():
        script = ua.build_fem_script(
            web_type,
            arm_length_mm,
            cell_size_mm,
            strut_radius_mm,
            force_n,
            mesh_max_size_mm,
            str(out_fcstd),
            material_id=str(mat["id"]),
        )
        fem_result = run_freecad_python(script, timeout=420)
        if fem_result and fem_result.get("ok"):
            result = fem_result
            result["stored_force_n"] = force_n
        elif settings.fem_allow_analytical_fallback:
            result = _load_precomputed_or_estimate(
                {"freecad_error": (fem_result or {}).get("error")}
            )
        else:
            return fem_result or {"ok": False, "error": "FEM failed and fallback disabled"}
    elif settings.fem_allow_analytical_fallback:
        result = _load_precomputed_or_estimate(
            {"warning": "FreeCAD not installed; using precomputed/estimate FEA."}
        )
    else:
        return {"ok": False, "error": "FreeCAD not installed and fallback disabled"}

    vm = result.get("max_von_mises_mpa")
    if vm:
        result["safety_factor_vs_yield"] = round(
            float(mat["yield_mpa"]) / float(vm), 3
        )
    result["ok"] = True
    result["part"] = "uav_arm"
    result["web_type"] = web_type
    result["force_n"] = force_n
    result["mesh_max_size_mm"] = mesh_max_size_mm
    result.setdefault("material", mats.describe(mat))
    result.setdefault("material_id", mat["id"])
    result.setdefault("yield_mpa", float(mat["yield_mpa"]))

    _STATE["results"] = result
    if result.get("fcstd_path"):
        _STATE["geometry"] = {**(geometry or {}), "fcstd_path": result["fcstd_path"]}

    if open_gui:
        gui_path = None
        if result.get("method") == "calculix_ccx" and result.get("fcstd_path"):
            gui_path = result["fcstd_path"]
        elif result.get("fcstd_path") and not result.get("fallback"):
            gui_path = result["fcstd_path"]
        if gui_path:
            result["gui"] = open_in_freecad_gui(gui_path)
        elif result.get("fallback"):
            result["gui"] = {
                "ok": False,
                "skipped": True,
                "reason": (
                    "FEA fell back to precomputed KPIs (no stress pipeline to show). "
                    "Retry solve; xtruss uses strut radius >= 1.5 mm and ~3.5 mm mesh."
                ),
            }

    _record_solve(result, geometry)
    result["results_path"] = _write_runtime_results(
        ua.precomputed_filename(web_type), result
    )
    return result


def apply_load_and_solve(
    force_n: float | None = None,
    mesh_max_size_mm: float | None = None,
    open_gui: bool = False,
) -> dict[str, Any]:
    """Mesh + CalculiX solve in FreeCAD; fall back to analytical/precomputed if needed."""
    settings = get_settings()
    geometry = _STATE.get("geometry")
    if not geometry:
        return {
            "ok": False,
            "error": (
                "No geometry. Call create_brake_pedal, create_uav_arm, "
                "or create_cantilever first."
            ),
        }

    if geometry.get("part") == "brake_pedal":
        force = float(force_n if force_n is not None else bp.DEFAULT_FORCE_N)
        mesh = float(
            mesh_max_size_mm if mesh_max_size_mm is not None else bp.DEFAULT_MESH_MM
        )
        return _apply_load_and_solve_brake_pedal(geometry, force, mesh, open_gui)

    if geometry.get("part") == "uav_arm":
        force = float(force_n if force_n is not None else ua.DEFAULT_FORCE_N)
        mesh = float(
            mesh_max_size_mm if mesh_max_size_mm is not None else ua.DEFAULT_MESH_MM
        )
        return _apply_load_and_solve_uav_arm(geometry, force, mesh, open_gui)

    force_n = float(force_n if force_n is not None else 100.0)
    mesh_max_size_mm = float(mesh_max_size_mm if mesh_max_size_mm is not None else 2.5)

    length_mm = float(geometry["length_mm"])
    width_mm = float(geometry["width_mm"])
    height_mm = float(geometry["height_mm"])
    cm = mats.get_material(geometry.get("material_id")) or mats.material_for_part(
        "cantilever"
    )
    cm_name = cm["display_name"]
    cm_e = float(cm["youngs_modulus_mpa"])
    cm_nu = float(cm["poissons_ratio"])
    cm_density = float(cm["density_kg_m3"])
    gate = validate_geometry_payload(
        {"length_mm": length_mm, "width_mm": width_mm, "height_mm": height_mm}
    )
    if gate:
        return gate

    analytical = analytical_cantilever_stress(
        length_mm, width_mm, height_mm, force_n, material=cm
    )
    out_fcstd = settings.workspace_dir / "cantilever_fem.FCStd"

    fem_result: dict[str, Any] | None = None
    if find_freecad_cmd():
        # Mirrors FreeCAD's ccx_cantilever_faceload example (Part::Box + Edge5 dir).
        script = f"""
import json
import traceback
import FreeCAD as App
import ObjectsFem
from femmesh import gmshtools
from femtools import ccxtools

try:
    doc = App.newDocument("CantileverFEM")
    length = float({length_mm})
    width = float({width_mm})
    height = float({height_mm})
    force = float({force_n})
    mesh_size = float({mesh_max_size_mm})

    geom = doc.addObject("Part::Box", "Beam")
    geom.Length = length
    geom.Width = width
    geom.Height = height
    doc.recompute()

    analysis = ObjectsFem.makeAnalysis(doc, "Analysis")
    solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiX")
    analysis.addObject(solver)

    material = ObjectsFem.makeMaterialSolid(doc, "MechanicalMaterial")
    mat = dict(material.Material)
    mat["Name"] = "{cm_name}"
    mat["YoungsModulus"] = "{cm_e} MPa"
    mat["PoissonRatio"] = "{cm_nu}"
    mat["Density"] = "{cm_density} kg/m^3"
    material.Material = mat
    analysis.addObject(material)

    fixed = ObjectsFem.makeConstraintFixed(doc, "ConstraintFixed")
    fixed.References = [(geom, "Face1")]
    analysis.addObject(fixed)

    force_obj = ObjectsFem.makeConstraintForce(doc, "ConstraintForce")
    force_obj.References = [(geom, "Face2")]
    force_obj.Force = "%s N" % force
    force_obj.Direction = (geom, ["Edge5"])
    force_obj.Reversed = True
    analysis.addObject(force_obj)

    mesh_obj = ObjectsFem.makeMeshGmsh(doc, "FEMMeshGmsh")
    mesh_obj.Shape = geom
    mesh_obj.CharacteristicLengthMax = "%s mm" % mesh_size
    mesh_obj.CharacteristicLengthMin = "%s mm" % (mesh_size / 2.0)
    analysis.addObject(mesh_obj)
    doc.recompute()

    gmshtools.GmshTools(mesh_obj).create_mesh()
    doc.recompute()
    n_nodes = int(mesh_obj.FemMesh.NodeCount)

    fea = ccxtools.FemToolsCcx(analysis)
    fea.update_objects()
    fea.setup_working_dir()
    fea.setup_ccx()
    fea.purge_results()
    fea.run()

    max_vm = None
    max_disp = None
    for obj in doc.Objects:
        vm = getattr(obj, "vonMises", None)
        if vm:
            max_vm = float(max(vm))
        disp = getattr(obj, "DisplacementLengths", None)
        if disp:
            max_disp = float(max(disp))

    fcstd_path = r"{out_fcstd}"
    for o in doc.Objects:
        try:
            o.Visibility = True
        except Exception:
            pass
    doc.saveAs(fcstd_path)

    if max_vm is None:
        raise RuntimeError("CalculiX finished but no von Mises results were found.")

    payload = {{
        "ok": True,
        "method": "calculix_ccx",
        "mesh_max_size_mm": mesh_size,
        "force_n": force,
        "length_mm": length,
        "width_mm": width,
        "height_mm": height,
        "node_count": n_nodes,
        "max_von_mises_mpa": round(max_vm, 4),
        "tip_deflection_mm": round(max_disp, 6) if max_disp is not None else None,
        "fcstd_path": fcstd_path,
        "note": (
            "Live FreeCAD FEM: Gmsh mesh + CalculiX. Coarse tets under-predict "
            "peak bending stress vs Euler-Bernoulli; compare analytical_reference_mpa."
        ),
    }}
except Exception:
    payload = {{"ok": False, "error": traceback.format_exc()}}
print("COMPANION_JSON:" + json.dumps(payload))
"""
        fem_result = run_freecad_python(script, timeout=300)

    if fem_result and fem_result.get("ok"):
        result = fem_result
        result["analytical_reference_mpa"] = analytical["max_von_mises_mpa"]
        result["material"] = analytical["material"]
        if result.get("tip_deflection_mm") is None:
            result["tip_deflection_mm"] = analytical["tip_deflection_mm"]
        result["analytical_tip_deflection_mm"] = analytical["tip_deflection_mm"]
    elif settings.fem_allow_analytical_fallback:
        result = analytical
        result["fallback"] = True
        if fem_result and not fem_result.get("ok"):
            result["freecad_error"] = fem_result.get("error")
    else:
        return fem_result or {"ok": False, "error": "FEM failed and fallback disabled"}

    result["ok"] = True
    result["force_n"] = force_n
    result["mesh_max_size_mm"] = mesh_max_size_mm
    result.setdefault("material", mats.describe(cm))
    result.setdefault("material_id", cm["id"])
    result.setdefault("yield_mpa", float(cm["yield_mpa"]))
    if result.get("max_von_mises_mpa") and not result.get("safety_factor_vs_yield"):
        result["safety_factor_vs_yield"] = round(
            float(cm["yield_mpa"]) / float(result["max_von_mises_mpa"]), 3
        )
    _STATE["results"] = result
    if result.get("fcstd_path"):
        _STATE["geometry"] = {
            **(geometry or {}),
            "fcstd_path": result["fcstd_path"],
        }

    if open_gui:
        gui_path = result.get("fcstd_path") or geometry.get("fcstd_path")
        if gui_path:
            result["gui"] = open_in_freecad_gui(gui_path)

    _record_solve(result, geometry)
    result["results_path"] = _write_runtime_results("cantilever_precomputed.json", result)
    return result


def get_max_von_mises() -> dict[str, Any]:
    results = _STATE.get("results")
    geometry = _STATE.get("geometry") or {}
    if not results:
        return {
            "ok": False,
            "error": "No results yet. Call apply_load_and_solve first.",
            "part": geometry.get("part"),
        }
    return {
        "ok": True,
        "max_von_mises_mpa": results.get("max_von_mises_mpa"),
        "analytical_reference_mpa": results.get("analytical_reference_mpa"),
        "pad_deflection_mm": results.get("pad_deflection_mm"),
        "method": results.get("method"),
        "force_n": results.get("force_n"),
        "tip_deflection_mm": results.get("tip_deflection_mm"),
        "material": results.get("material"),
        "part": results.get("part") or geometry.get("part"),
        "web_type": results.get("web_type"),
        "mass_kg": results.get("mass_kg"),
        "relative_density": results.get("relative_density"),
        "safety_factor_vs_yield": results.get("safety_factor_vs_yield"),
    }


def _run_row(run: dict[str, Any]) -> dict[str, Any]:
    """Compact per-run row for query_results listing (F06)."""
    return {
        "run_id": run.get("run_id"),
        "part": run.get("part"),
        "web_type": run.get("web_type"),
        "force_n": run.get("force_n"),
        "method": run.get("method"),
        "max_von_mises_mpa": run.get("max_von_mises_mpa"),
        "max_vm_location_mm": run.get("max_vm_location_mm"),
        "safety_factor_vs_yield": run.get("safety_factor_vs_yield"),
        "mesh_max_size_mm": run.get("mesh_max_size_mm"),
        "divergence_flag": run.get("divergence_flag"),
        "ts": run.get("ts"),
    }


def query_results(
    part: str | None = None,
    run_id: str | None = None,
    last_n: int = 10,
) -> dict[str, Any]:
    """F06: query the stored per-run solve history for a part.

    Default call returns the latest run in full plus a compact table of the
    most recent runs (newest first). "Where is stress concentrated" is the
    latest run's max_vm_location_mm. Every run carries its method flag and
    mesh size; reaction forces are not captured.
    """
    settings = get_settings()
    settings.ensure_dirs()
    key = str(part or "").strip() or None
    if key and key not in dp.KNOWN_PARTS:
        return {
            "ok": False,
            "error": f"unknown part {part!r}; known parts: {list(dp.KNOWN_PARTS)}",
            "error_class": "bad_params",
            "correction": (
                "Use one of brake_pedal, cantilever, uav_arm "
                "(or omit part to use the active one)."
            ),
        }
    rid = str(run_id or "").strip() or None
    if rid:
        found = rh.find_run(rid, key)
        if not found:
            return {
                "ok": False,
                "error": f"No stored run with run_id {rid!r}.",
                "error_class": "no_results",
                "correction": (
                    "Call query_results without run_id to list recent runs, "
                    "or apply_load_and_solve to create a new one."
                ),
            }
        return {
            "ok": True,
            "run": found,
            "reactions": "not captured (planned with F10 load-case params)",
        }
    if not key:
        key = _active_part()
    if not key:
        return {
            "ok": False,
            "error": (
                "No active part and no part given; no results yet this session."
            ),
            "error_class": "no_results",
            "correction": (
                "Call apply_load_and_solve first, or pass part=brake_pedal to "
                "read that part's stored history."
            ),
        }
    try:
        count = max(1, min(int(last_n or 10), 50))
    except (TypeError, ValueError):
        count = 10
    runs = rh.read_runs(key, last_n=count)
    if not runs:
        return {
            "ok": False,
            "error": f"No stored runs for {key} yet.",
            "error_class": "no_results",
            "correction": f"Call apply_load_and_solve on {key} first, then retry.",
        }
    latest = runs[-1]
    return {
        "ok": True,
        "part": key,
        "latest": latest,
        "max_vm_location_mm": latest.get("max_vm_location_mm"),
        "runs": [_run_row(run) for run in reversed(runs)],
        "run_count": len(runs),
        "reactions": "not captured (planned with F10 load-case params)",
        "note": (
            "Each run states its method (calculix_ccx / precomputed_demo_estimate "
            "/ analytical) and mesh size. Not verified: reaction forces and "
            "local stress refinement around the peak node."
        ),
    }


def open_current_in_freecad() -> dict[str, Any]:
    """Open the latest CAD/FEM document in the FreeCAD GUI."""
    geometry = _STATE.get("geometry") or {}
    results = _STATE.get("results") or {}
    path = results.get("fcstd_path") or geometry.get("fcstd_path")
    settings = get_settings()
    part = str(geometry.get("part") or results.get("part") or "")
    web = str(geometry.get("web_type") or results.get("web_type") or "")
    if not path:
        candidates: list[Path] = []
        if part == "brake_pedal":
            wt = bp.normalize_web_type(web or "xtruss")
            candidates = [
                settings.workspace_dir / f"brake_pedal_{wt}_fem.FCStd",
                settings.workspace_dir / f"brake_pedal_{wt}.FCStd",
            ]
        elif part == "uav_arm":
            wt = ua.normalize_web_type(web or "solid")
            candidates = [
                settings.workspace_dir / f"uav_arm_{wt}_fem.FCStd",
                settings.workspace_dir / f"uav_arm_{wt}.FCStd",
            ]
        elif part == "cantilever":
            candidates = [
                settings.workspace_dir / "cantilever_fem.FCStd",
                settings.workspace_dir / "cantilever.FCStd",
            ]
        else:
            candidates = [
                settings.workspace_dir / "brake_pedal_xtruss_fem.FCStd",
                settings.workspace_dir / "brake_pedal_xtruss.FCStd",
                settings.workspace_dir / "cantilever_fem.FCStd",
                settings.workspace_dir / "cantilever.FCStd",
            ]
        for candidate in candidates:
            if candidate.exists():
                path = str(candidate)
                break
    if not path:
        return {
            "ok": False,
            "error": "No FreeCAD document yet. Create/solve a model first.",
        }
    return open_in_freecad_gui(path)


def load_precomputed_results(case: str = "auto") -> dict[str, Any]:
    """Load saved FEA KPIs from data/results/.

    case: auto|cantilever|brake_pedal|brake_solid|brake_bcc|brake_fcc|
          brake_pedal_solid|...
    """
    settings = get_settings()
    key = (case or "auto").lower().strip()
    mapping = {
        "cantilever": "cantilever_precomputed.json",
        "brake_pedal": bp.precomputed_filename("xtruss"),
        "brake_solid": bp.precomputed_filename("solid"),
        "brake_bcc": bp.precomputed_filename("xtruss"),
        "brake_xtruss": bp.precomputed_filename("xtruss"),
        "brake_fcc": bp.precomputed_filename("fcc"),
        "brake_pedal_solid": bp.precomputed_filename("solid"),
        "brake_pedal_bcc": bp.precomputed_filename("xtruss"),
        "brake_pedal_xtruss": bp.precomputed_filename("xtruss"),
        "brake_pedal_fcc": bp.precomputed_filename("fcc"),
        "uav_arm": ua.precomputed_filename("xtruss"),
        "uav_solid": ua.precomputed_filename("solid"),
        "uav_xtruss": ua.precomputed_filename("xtruss"),
        "uav_arm_solid": ua.precomputed_filename("solid"),
        "uav_arm_xtruss": ua.precomputed_filename("xtruss"),
    }
    if key == "auto":
        geo = _STATE.get("geometry") or {}
        res = _STATE.get("results") or {}
        if geo.get("part") == "uav_arm" or res.get("part") == "uav_arm":
            wt = ua.normalize_web_type(str(geo.get("web_type") or res.get("web_type") or "solid"))
            key = f"uav_{wt}" if wt in ua.WEB_TYPES else "uav_xtruss"
        elif geo.get("part") == "brake_pedal" or res.get("part") == "brake_pedal":
            wt = bp.normalize_web_type(str(geo.get("web_type") or res.get("web_type") or "xtruss"))
            key = f"brake_{wt}" if wt in bp.WEB_TYPES else "brake_xtruss"
        else:
            if (settings.results_dir / bp.precomputed_filename("xtruss")).exists():
                key = "brake_xtruss"
            else:
                key = "cantilever"

    brake_keys = {
        "brake_pedal",
        "brake_solid",
        "brake_bcc",
        "brake_xtruss",
        "brake_fcc",
        "brake_pedal_solid",
        "brake_pedal_bcc",
        "brake_pedal_xtruss",
        "brake_pedal_fcc",
    }
    uav_keys = {
        "uav_arm",
        "uav_solid",
        "uav_xtruss",
        "uav_arm_solid",
        "uav_arm_xtruss",
    }
    if key in uav_keys:
        if key == "uav_arm":
            wt = "xtruss"
        elif key.startswith("uav_arm_"):
            wt = key.replace("uav_arm_", "")
        else:
            wt = key.replace("uav_", "")
        fname = ua.precomputed_filename(ua.normalize_web_type(wt))
    elif key in brake_keys:
        if key == "brake_pedal":
            wt = "xtruss"
        elif key.startswith("brake_pedal_"):
            wt = key.replace("brake_pedal_", "")
        else:
            wt = key.replace("brake_", "")
        fname = bp.precomputed_filename(bp.normalize_web_type(wt))
    else:
        fname = mapping.get(key, mapping["cantilever"])

    path = settings.results_dir / fname
    if not path.exists():
        if key in brake_keys or key.startswith("brake_"):
            wt = "xtruss"
            if key.startswith("brake_pedal_"):
                wt = key.replace("brake_pedal_", "")
            elif key.startswith("brake_") and key != "brake_pedal":
                wt = key.replace("brake_", "")
            wt = bp.normalize_web_type(wt)
            if wt not in bp.WEB_TYPES:
                wt = "xtruss"
            data = bp.fallback_fea_result(wt, bp.DEFAULT_FORCE_N)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        elif key in uav_keys or key.startswith("uav_"):
            wt = "xtruss"
            if key.startswith("uav_arm_"):
                wt = key.replace("uav_arm_", "")
            elif key.startswith("uav_") and key != "uav_arm":
                wt = key.replace("uav_", "")
            wt = ua.normalize_web_type(wt)
            if wt not in ua.WEB_TYPES:
                wt = "xtruss"
            data = ua.fallback_fea_result(wt, ua.DEFAULT_FORCE_N)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        else:
            return {"ok": False, "error": f"Missing {path}"}
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    _STATE["results"] = data
    if data.get("part") == "brake_pedal":
        _STATE["geometry"] = {
            **(
                bp.memory_geometry(
                    bp.normalize_web_type(str(data.get("web_type", "xtruss"))),
                    float(data.get("cell_size_mm", bp.DEFAULT_CELL_SIZE_MM)),
                    float(data.get("strut_radius_mm", bp.DEFAULT_STRUT_RADIUS_MM)),
                    "Loaded from precomputed results.",
                )
            ),
            **{
                k: data.get(k)
                for k in ("volume_mm3", "mass_kg", "relative_density")
                if data.get(k) is not None
            },
            "part": "brake_pedal",
            "web_type": bp.normalize_web_type(str(data.get("web_type", "xtruss"))),
        }
    elif data.get("part") == "uav_arm":
        _STATE["geometry"] = {
            **ua.memory_geometry(
                ua.normalize_web_type(str(data.get("web_type", "solid"))),
                float(data.get("arm_length_mm", ua.ARM_LENGTH_MM)),
                float(data.get("cell_size_mm", ua.DEFAULT_CELL_SIZE_MM)),
                float(data.get("strut_radius_mm", ua.DEFAULT_STRUT_RADIUS_MM)),
                "Loaded from precomputed results.",
            ),
            "part": "uav_arm",
            "web_type": ua.normalize_web_type(str(data.get("web_type", "solid"))),
        }
    return {"ok": True, "results": data, "path": str(path), "case": key}


TOOL_SPECS = [
    {
        "name": "create_brake_pedal",
        "description": (
            "Create a brake-pedal lattice bracket (pivot + clevis rings + footpad) "
            "with web_type solid|xtruss|fcc lattice fill, export STEP/STL, open FreeCAD GUI. "
            "Material defaults to Al 6061-T6."
        ),
        "parameters": {
            "web_type": "solid|xtruss|fcc, default xtruss (bcc aliases to xtruss)",
            "cell_size_mm": "float, default 15",
            "strut_radius_mm": "float, default 2.5 (xtruss strut thickness / fcc radius)",
            "material": (
                "material id or alias, default al6061t6; one of al6061t6, "
                "al7075t6, ti6al4v, pa12, steel ('ti', '7075', 'nylon' work too)"
            ),
            "open_gui": "bool, default false",
        },
    },
    {
        "name": "create_uav_arm",
        "description": (
            "Create the flagship UAV arm (root clamp boss + tapered arm + tip "
            "motor-mount ring), web_type solid|xtruss (chord rails + exposed "
            "X-truss web), export STEP/STL, open FreeCAD GUI. Demo load case: "
            "120 N tip thrust at the motor ring. Material defaults to Al 6061-T6."
        ),
        "parameters": {
            "web_type": "solid|xtruss, default solid (bcc/x-truss alias to xtruss)",
            "arm_length_mm": "float, default 180 (editable range 120-320)",
            "cell_size_mm": "float, default 12 (editable range 6-30)",
            "strut_radius_mm": "float, default 1.8 (editable range 1.5-4; 1.5 = meshable minimum)",
            "material": (
                "material id or alias, default al6061t6; one of al6061t6, "
                "al7075t6, ti6al4v, pa12, steel"
            ),
            "open_gui": "bool, default false",
        },
    },
    {
        "name": "get_lattice_metrics",
        "description": (
            "Return relative density, volumes, and mass estimate for the current "
            "brake-pedal geometry."
        ),
        "parameters": {},
    },
    {
        "name": "compare_brake_pedal_variants",
        "description": (
            "Compare solid vs X-truss vs FCC brake-pedal mass, relative density, "
            "max von Mises, pad deflection; recommend lightest with SF>=1.5 "
            "against the program material's yield."
        ),
        "parameters": {},
    },
    {
        "name": "compare_materials",
        "description": (
            "F09 material comparison for a part: rows for every table material "
            "(Al 6061-T6, Al 7075-T6, Ti-6Al-4V, PA12, Steel-Generic) with mass, "
            "max von Mises, safety factor vs that material's yield, and scaled "
            "deflection, ranked by lightest at SF>=1.5. Scales the best available "
            "base run (session -> run history -> precomputed; labeled per row) "
            "linear-elastically; PA12 deflection is flagged not verified. Every "
            "row carries citation sources."
        ),
        "parameters": {
            "part": "brake_pedal|cantilever|uav_arm, default = active part (else brake_pedal)",
        },
    },
    {
        "name": "get_design_program",
        "description": (
            "Return the persisted design program (source of truth) for a part: "
            "editable params, read-only fixed constants, revision number, and "
            "params hash. Defaults to the active part; with no active part, "
            "lists the programs on disk."
        ),
        "parameters": {
            "part": "brake_pedal|cantilever|uav_arm, default = active part",
        },
    },
    {
        "name": "update_design_program",
        "description": (
            "Edit the design program and rebuild the part in one step "
            "(e.g. 'set cell size to 12' without recreating): merges changes "
            "over current params, range-preflights (hard reject, never clamps), "
            "rebuilds geometry, commits the new revision on success. A failed "
            "rebuild preserves the accepted revision; a no-op change does not "
            "rebuild or bump the revision."
        ),
        "parameters": {
            "part": "brake_pedal|cantilever|uav_arm, default = active part",
            "changes": (
                "object of param -> value, e.g. {\"cell_size_mm\": 12}; editable: "
                "web_type, cell_size_mm [5,40], strut_radius_mm [1,5], material "
                "(al6061t6|al7075t6|ti6al4v|pa12|steel; aliases like 'ti', "
                "'7075', 'nylon' accepted) for lattice parts; arm_length_mm "
                "[120,320], cell_size_mm [6,30], strut_radius_mm [1.5,4] for "
                "the uav_arm; or length_mm [10,500], width_mm [2,100], "
                "height_mm [1,50], material for the cantilever"
            ),
            "dry_run": "bool, default false — preflight + hash preview only, no rebuild",
            "open_gui": "bool, default false",
        },
    },
    {
        "name": "create_cantilever",
        "description": (
            "Create a rectangular cantilever beam (mm), export STEP/STL, "
            "and open the model in the FreeCAD GUI. Material defaults to "
            "Steel-Generic."
        ),
        "parameters": {
            "length_mm": "float, default 100",
            "width_mm": "float, default 20",
            "height_mm": "float, default 5",
            "material": (
                "material id or alias, default steel; one of al6061t6, "
                "al7075t6, ti6al4v, pa12, steel"
            ),
            "open_gui": "bool, default false",
        },
    },
    {
        "name": "apply_load_and_solve",
        "description": (
            "Apply load (N), mesh with Gmsh, solve with CalculiX inside FreeCAD "
            "(brake-pedal footpad, UAV-arm motor ring, or cantilever tip), save "
            "results, open GUI. Requires create_brake_pedal, create_uav_arm, or "
            "create_cantilever first."
        ),
        "parameters": {
            "force_n": (
                "float, default 500 brake pedal / 120 uav arm / 100 cantilever"
            ),
            "mesh_max_size_mm": (
                "float, default 5 (pedal) / 3.5 (uav arm) / 2.5 (cantilever)"
            ),
            "open_gui": "bool, default false",
        },
    },
    {
        "name": "get_max_von_mises",
        "description": "Return max von Mises stress (MPa) from the latest solve.",
        "parameters": {},
    },
    {
        "name": "query_results",
        "description": (
            "Query the stored per-run solve history: latest run in full (mass, "
            "max von Mises + its location, deflection, mesh size, method flag, "
            "expected-vs-actual divergence) plus a compact list of recent runs. "
            "'Where is stress concentrated' = max_vm_location_mm of the latest run."
        ),
        "parameters": {
            "part": "brake_pedal|cantilever|uav_arm, default = active part",
            "run_id": "optional run id from a previous solve (returns that run only)",
            "last_n": "int, default 10 (capped at 50) runs listed",
        },
    },
    {
        "name": "run_convergence_study",
        "description": (
            "Mesh convergence study for the active part: 2-3 live CalculiX "
            "solves at refining mesh sizes (default ladder = 1.0x/0.7x/0.5x "
            "of the part default, e.g. pedal 5/3.5/2.5 mm), then a "
            "recommended mesh size = the coarsest mesh within 5% of the "
            "finest max von Mises. Synchronous and headless; expect roughly "
            "the cost of 2-3 apply_load_and_solve calls. Refuses setups "
            "without live solves (fcc pedal precomputed KPIs, FreeCAD absent)."
        ),
        "parameters": {
            "mesh_sizes_mm": (
                "optional explicit list of 2-4 distinct mesh sizes in mm "
                "(coarse -> fine); default = multiplier ladder of the part default"
            ),
            "force_n": (
                "optional load in N; default = same as apply_load_and_solve "
                "for the part (500 pedal / 100 cantilever)"
            ),
        },
    },
    {
        "name": "open_in_freecad",
        "description": "Launch FreeCAD GUI with the latest CAD/FEM document.",
        "parameters": {},
    },
]


def call_tool(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch a tool and wrap the result in the F02 outcome envelope."""
    return outcome.wrap_tool_call(name, args or {}, _call_tool_raw, state_fn=get_state)


def _call_tool_raw(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "create_brake_pedal":
        return create_brake_pedal(
            web_type=str(args.get("web_type", "xtruss")),
            cell_size_mm=float(args.get("cell_size_mm", bp.DEFAULT_CELL_SIZE_MM)),
            strut_radius_mm=float(
                args.get("strut_radius_mm", bp.DEFAULT_STRUT_RADIUS_MM)
            ),
            open_gui=bool(args.get("open_gui", False)),
            material=str(args.get("material", mats.DEFAULT_PART_MATERIAL["brake_pedal"])),
        )
    if name == "create_uav_arm":
        return create_uav_arm(
            web_type=str(args.get("web_type", "solid")),
            arm_length_mm=float(args.get("arm_length_mm", ua.ARM_LENGTH_MM)),
            cell_size_mm=float(args.get("cell_size_mm", ua.DEFAULT_CELL_SIZE_MM)),
            strut_radius_mm=float(
                args.get("strut_radius_mm", ua.DEFAULT_STRUT_RADIUS_MM)
            ),
            open_gui=bool(args.get("open_gui", False)),
            material=str(args.get("material", mats.DEFAULT_PART_MATERIAL["uav_arm"])),
        )
    if name == "get_lattice_metrics":
        return get_lattice_metrics()
    if name == "compare_brake_pedal_variants":
        return compare_brake_pedal_variants()
    if name == "compare_materials":
        return compare_materials(part=str(args["part"]) if args.get("part") else None)
    if name == "create_cantilever":
        return create_cantilever(
            length_mm=float(args.get("length_mm", 100)),
            width_mm=float(args.get("width_mm", 20)),
            height_mm=float(args.get("height_mm", 5)),
            open_gui=bool(args.get("open_gui", False)),
            material=str(args.get("material", mats.DEFAULT_PART_MATERIAL["cantilever"])),
        )
    if name == "apply_load_and_solve":
        force = args.get("force_n")
        mesh = args.get("mesh_max_size_mm")
        return apply_load_and_solve(
            force_n=float(force) if force is not None else None,
            mesh_max_size_mm=float(mesh) if mesh is not None else None,
            open_gui=bool(args.get("open_gui", False)),
        )
    if name == "get_max_von_mises":
        return get_max_von_mises()
    if name == "query_results":
        return query_results(
            part=str(args["part"]) if args.get("part") else None,
            run_id=str(args["run_id"]) if args.get("run_id") else None,
            last_n=int(args.get("last_n", 10) or 10),
        )
    if name == "get_design_program":
        return get_design_program(
            part=str(args["part"]) if args.get("part") else None,
        )
    if name == "update_design_program":
        return update_design_program(
            part=str(args["part"]) if args.get("part") else None,
            changes=args.get("changes") if args.get("changes") is not None else None,
            dry_run=bool(args.get("dry_run", False)),
            open_gui=bool(args.get("open_gui", False)),
        )
    if name == "run_convergence_study":
        # Lazy import: convergence imports this module for the solve seam.
        from companion.tools import convergence

        force = args.get("force_n")
        return convergence.run_convergence_study(
            mesh_sizes_mm=args.get("mesh_sizes_mm"),
            force_n=float(force) if force is not None else None,
        )
    if name == "open_in_freecad":
        return open_current_in_freecad()
    return {"ok": False, "error": f"Unknown tool: {name}"}
