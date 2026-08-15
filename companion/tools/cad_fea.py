"""CAD/FEA tools: cantilever + engine-mount + brake-pedal lattice creation and coarse static analysis."""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

from companion.config import get_settings
from companion.tools import brake_pedal as bp
from companion.tools import engine_mount as em
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
        _current_thread_id.reset(token)


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
) -> dict[str, Any]:
    """Euler-Bernoulli cantilever with tip load (bending about weak axis height).

    Beam along X, cross-section width (Y) x height (Z), load in -Z.
    sigma_max = 6*F*L / (b * h^2)  [N/mm^2 = MPa]
    delta_max = F*L^3 / (3*E*I)
    """
    length_m = length_mm / 1000.0
    width_m = width_mm / 1000.0
    height_m = height_mm / 1000.0
    e_pa = 210e9  # steel
    i = width_m * height_m**3 / 12.0
    sigma_mpa = (6.0 * force_n * length_mm) / (width_mm * height_mm**2)
    tip_defl_mm = (force_n * length_m**3 / (3.0 * e_pa * i)) * 1000.0
    return {
        "ok": True,
        "method": "analytical_euler_bernoulli",
        "material": "Steel approx E=210 GPa, nu=0.3",
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
    open_gui: bool = True,
) -> dict[str, Any]:
    """Create a rectangular cantilever solid with FreeCAD and export STEP/STL."""
    settings = get_settings()
    settings.ensure_dirs()
    out_step = settings.exports_dir / "cantilever.step"
    out_stl = settings.exports_dir / "cantilever.stl"
    out_fcstd = settings.workspace_dir / "cantilever.FCStd"

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
        if open_gui and result.get("fcstd_path"):
            gui = open_in_freecad_gui(result["fcstd_path"])
            result["gui"] = gui
    return result


def create_engine_mount(
    web_type: str = "bcc",
    cell_size_mm: float = em.DEFAULT_CELL_SIZE_MM,
    strut_radius_mm: float = em.DEFAULT_STRUT_RADIUS_MM,
    open_gui: bool = True,
) -> dict[str, Any]:
    """Create L-bracket engine mount with solid or lattice web; export STEP/STL."""
    settings = get_settings()
    settings.ensure_dirs()
    wt = str(web_type or "bcc").lower().strip()
    if wt not in em.WEB_TYPES:
        return {
            "ok": False,
            "error": f"web_type must be one of {sorted(em.WEB_TYPES)}, got {web_type!r}",
        }

    out_step = settings.exports_dir / f"engine_mount_{wt}.step"
    out_stl = settings.exports_dir / f"engine_mount_{wt}.stl"
    out_fcstd = settings.workspace_dir / f"engine_mount_{wt}.FCStd"
    script = em.build_geometry_script(
        wt, cell_size_mm, strut_radius_mm, str(out_step), str(out_stl), str(out_fcstd)
    )

    if not find_freecad_cmd():
        result = em.memory_geometry(
            wt,
            cell_size_mm,
            strut_radius_mm,
            "FreeCAD not installed; geometry recorded in memory only.",
        )
    else:
        result = run_freecad_python(script, timeout=180)
        if not result.get("ok"):
            freecad_error = result.get("error", "unknown")
            result = em.memory_geometry(
                wt,
                cell_size_mm,
                strut_radius_mm,
                f"FreeCADCmd failed ({freecad_error}); geometry recorded in memory only.",
            )
            result["freecad_error"] = freecad_error

    if result.get("ok"):
        _STATE["geometry"] = result
        _STATE["results"] = None
        if open_gui and result.get("fcstd_path"):
            result["gui"] = open_in_freecad_gui(result["fcstd_path"])
    return result


def create_brake_pedal(
    web_type: str = "xtruss",
    cell_size_mm: float = bp.DEFAULT_CELL_SIZE_MM,
    strut_radius_mm: float = bp.DEFAULT_STRUT_RADIUS_MM,
    open_gui: bool = True,
) -> dict[str, Any]:
    """Create brake-pedal bracket with solid or lattice web; export STEP/STL."""
    settings = get_settings()
    settings.ensure_dirs()
    wt = bp.normalize_web_type(web_type)
    if wt not in bp.WEB_TYPES:
        return {
            "ok": False,
            "error": f"web_type must be one of {sorted(bp.WEB_TYPES)}, got {web_type!r}",
        }

    out_step = settings.exports_dir / f"brake_pedal_{wt}.step"
    out_stl = settings.exports_dir / f"brake_pedal_{wt}.stl"
    out_fcstd = settings.workspace_dir / f"brake_pedal_{wt}.FCStd"
    script = bp.build_geometry_script(
        wt, cell_size_mm, strut_radius_mm, str(out_step), str(out_stl), str(out_fcstd)
    )

    if not find_freecad_cmd():
        result = bp.memory_geometry(
            wt,
            cell_size_mm,
            strut_radius_mm,
            "FreeCAD not installed; geometry recorded in memory only.",
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
            )
            result["freecad_error"] = freecad_error

    if result.get("ok"):
        _STATE["geometry"] = result
        _STATE["results"] = None
        if open_gui and result.get("fcstd_path"):
            result["gui"] = open_in_freecad_gui(result["fcstd_path"])
    return result


def get_lattice_metrics() -> dict[str, Any]:
    """Relative density, volumes, and mass for current lattice geometry (mount or pedal)."""
    geometry = _STATE.get("geometry")
    part = (geometry or {}).get("part")
    if not geometry or part not in ("engine_mount", "brake_pedal"):
        return {
            "ok": False,
            "error": (
                "No lattice geometry. Call create_brake_pedal or create_engine_mount first."
            ),
        }
    mod = bp if part == "brake_pedal" else em
    vols = mod.estimate_part_volume_mm3(
        str(geometry.get("web_type", "xtruss" if part == "brake_pedal" else "bcc")),
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
        "yield_mpa": geometry.get("yield_mpa", mod.AL_YIELD_MPA),
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


def compare_mount_variants() -> dict[str, Any]:
    """Compare solid / BCC / FCC mount KPIs from session or precomputed JSON."""
    settings = get_settings()
    settings.ensure_dirs()
    variants: list[dict[str, Any]] = []
    session = _STATE.get("results") or {}
    session_geo = _STATE.get("geometry") or {}

    for wt in ("solid", "bcc", "fcc"):
        row: dict[str, Any] | None = None
        if (
            session.get("part") == "engine_mount"
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
        path = settings.results_dir / em.precomputed_filename(wt)
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
                "force_n": data.get("force_n", em.DEFAULT_FORCE_N),
                "method": data.get("method"),
            }
        if row is None:
            est = em.fallback_fea_result(wt, em.DEFAULT_FORCE_N)
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
        # Fill mass/rho from geometry estimates if missing
        if row.get("mass_kg") is None or row.get("relative_density") is None:
            vols = em.estimate_part_volume_mm3(wt)
            row.setdefault("mass_kg", vols["mass_kg"])
            row.setdefault("relative_density", vols["relative_density"])
        vm = row.get("max_von_mises_mpa")
        row["safety_factor_vs_yield"] = (
            round(em.AL_YIELD_MPA / float(vm), 3) if vm else None
        )
        variants.append(row)

    # Recommend lightest that still SF >= 1.5 (demo threshold).
    ok_sf = [v for v in variants if (v.get("safety_factor_vs_yield") or 0) >= 1.5]
    if ok_sf:
        recommendation = min(ok_sf, key=lambda v: float(v.get("mass_kg") or 1e9))
    else:
        recommendation = max(
            variants, key=lambda v: float(v.get("safety_factor_vs_yield") or 0)
        )

    return {
        "ok": True,
        "part": "engine_mount",
        "yield_mpa": em.AL_YIELD_MPA,
        "sf_threshold": 1.5,
        "variants": variants,
        "recommendation": recommendation,
        "session_web_type": session_geo.get("web_type"),
        "note": (
            "Compare mass, relative density, max von Mises, and pad deflection. "
            "Recommend lowest mass with SF>=1.5 vs Al 6061-T6 yield (~276 MPa)."
        ),
    }


def compare_brake_pedal_variants() -> dict[str, Any]:
    """Compare solid / X-truss / FCC brake-pedal KPIs from session or precomputed JSON."""
    settings = get_settings()
    settings.ensure_dirs()
    variants: list[dict[str, Any]] = []
    session = _STATE.get("results") or {}
    session_geo = _STATE.get("geometry") or {}

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
            round(bp.AL_YIELD_MPA / float(vm), 3) if vm else None
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
        "yield_mpa": bp.AL_YIELD_MPA,
        "sf_threshold": 1.5,
        "variants": variants,
        "recommendation": recommendation,
        "session_web_type": session_geo.get("web_type"),
        "note": (
            "Compare mass, relative density, max von Mises, and pad deflection. "
            "Recommend lowest mass with SF>=1.5 vs Al 6061-T6 yield (~276 MPa)."
        ),
    }


def _apply_load_and_solve_engine_mount(
    geometry: dict[str, Any],
    force_n: float,
    mesh_max_size_mm: float,
    open_gui: bool,
) -> dict[str, Any]:
    settings = get_settings()
    settings.ensure_dirs()
    web_type = str(geometry.get("web_type", "bcc")).lower()
    cell_size_mm = float(geometry.get("cell_size_mm", em.DEFAULT_CELL_SIZE_MM))
    strut_radius_mm = float(
        geometry.get("strut_radius_mm", em.DEFAULT_STRUT_RADIUS_MM)
    )
    # Thin BCC struts (r<2.0) mesh empty in Gmsh → no CalculiX stress plot.
    if web_type in ("bcc", "fcc") and strut_radius_mm < 2.0:
        strut_radius_mm = em.DEFAULT_STRUT_RADIUS_MM
    precomputed_path = settings.results_dir / em.precomputed_filename(web_type)
    out_fcstd = settings.workspace_dir / f"engine_mount_{web_type}_fem.FCStd"

    def _load_precomputed_or_estimate(extra: dict[str, Any] | None = None) -> dict[str, Any]:
        if precomputed_path.exists():
            data = json.loads(precomputed_path.read_text(encoding="utf-8"))
            data = _scale_precomputed_force(data, force_n)
            if extra:
                data.update(extra)
                data["force_n"] = force_n
            return data
        return em.fallback_fea_result(web_type, force_n, geometry)

    fem_result: dict[str, Any] | None = None
    # FCC: geometry + metrics + precomputed FEA only (mesh cost / demo reliability).
    if web_type == "fcc":
        result = _load_precomputed_or_estimate(
            {"note": "FCC FEA uses precomputed/demo KPIs (no live continuum solve)."}
        )
    elif find_freecad_cmd():
        script = em.build_fem_script(
            web_type,
            cell_size_mm,
            strut_radius_mm,
            force_n,
            mesh_max_size_mm,
            str(out_fcstd),
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
        result["safety_factor_vs_yield"] = round(em.AL_YIELD_MPA / float(vm), 3)
    result["ok"] = True
    result["part"] = "engine_mount"
    result["web_type"] = web_type
    result["force_n"] = force_n
    result["mesh_max_size_mm"] = mesh_max_size_mm
    result.setdefault("material", "Al 6061-T6 approx E=69 GPa, nu=0.33")
    result.setdefault("yield_mpa", em.AL_YIELD_MPA)

    _STATE["results"] = result
    if result.get("fcstd_path"):
        _STATE["geometry"] = {**(geometry or {}), "fcstd_path": result["fcstd_path"]}

    if open_gui:
        # Only open a document that contains FEM results. Opening the CAD-only
        # create() file after a failed solve looks like "lattice with no stress".
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
                    "Retry solve; BCC needs strut_radius_mm>=2.2 for a live mesh."
                ),
            }

    result["results_path"] = _write_runtime_results(
        em.precomputed_filename(web_type), result
    )
    return result


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
    # FCC continuum needs thicker struts for a usable Gmsh volume mesh.
    if web_type == "fcc" and strut_radius_mm < 2.0:
        strut_radius_mm = 2.2
    precomputed_path = settings.results_dir / bp.precomputed_filename(web_type)
    out_fcstd = settings.workspace_dir / f"brake_pedal_{web_type}_fem.FCStd"

    def _load_precomputed_or_estimate(extra: dict[str, Any] | None = None) -> dict[str, Any]:
        if precomputed_path.exists():
            data = json.loads(precomputed_path.read_text(encoding="utf-8"))
            data = _scale_precomputed_force(data, force_n)
            if extra:
                data.update(extra)
                data["force_n"] = force_n
            return data
        return bp.fallback_fea_result(web_type, force_n, geometry)

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
        result["safety_factor_vs_yield"] = round(bp.AL_YIELD_MPA / float(vm), 3)
    result["ok"] = True
    result["part"] = "brake_pedal"
    result["web_type"] = web_type
    result["force_n"] = force_n
    result["mesh_max_size_mm"] = mesh_max_size_mm
    result.setdefault("material", "Al 6061-T6 approx E=69 GPa, nu=0.33")
    result.setdefault("yield_mpa", bp.AL_YIELD_MPA)

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

    result["results_path"] = _write_runtime_results(
        bp.precomputed_filename(web_type), result
    )
    return result


def apply_load_and_solve(
    force_n: float | None = None,
    mesh_max_size_mm: float | None = None,
    open_gui: bool = True,
) -> dict[str, Any]:
    """Mesh + CalculiX solve in FreeCAD; fall back to analytical/precomputed if needed."""
    settings = get_settings()
    geometry = _STATE.get("geometry")
    if not geometry:
        return {
            "ok": False,
            "error": (
                "No geometry. Call create_brake_pedal, create_engine_mount, "
                "or create_cantilever first."
            ),
        }

    if geometry.get("part") == "brake_pedal":
        force = float(force_n if force_n is not None else bp.DEFAULT_FORCE_N)
        mesh = float(
            mesh_max_size_mm if mesh_max_size_mm is not None else bp.DEFAULT_MESH_MM
        )
        return _apply_load_and_solve_brake_pedal(geometry, force, mesh, open_gui)

    if geometry.get("part") == "engine_mount":
        force = float(force_n if force_n is not None else em.DEFAULT_FORCE_N)
        mesh = float(mesh_max_size_mm if mesh_max_size_mm is not None else em.DEFAULT_MESH_MM)
        return _apply_load_and_solve_engine_mount(geometry, force, mesh, open_gui)

    force_n = float(force_n if force_n is not None else 100.0)
    mesh_max_size_mm = float(mesh_max_size_mm if mesh_max_size_mm is not None else 2.5)

    length_mm = float(geometry["length_mm"])
    width_mm = float(geometry["width_mm"])
    height_mm = float(geometry["height_mm"])

    analytical = analytical_cantilever_stress(length_mm, width_mm, height_mm, force_n)
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
    mat["Name"] = "Steel-Generic"
    mat["YoungsModulus"] = "210000 MPa"
    mat["PoissonRatio"] = "0.30"
    mat["Density"] = "7900 kg/m^3"
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
        "geometry": _STATE.get("geometry"),
        "full_results": results,
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
        elif part == "engine_mount":
            wt = web or "bcc"
            candidates = [
                settings.workspace_dir / f"engine_mount_{wt}_fem.FCStd",
                settings.workspace_dir / f"engine_mount_{wt}.FCStd",
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
                settings.workspace_dir / "engine_mount_bcc_fem.FCStd",
                settings.workspace_dir / "engine_mount_solid_fem.FCStd",
                settings.workspace_dir / "engine_mount_bcc.FCStd",
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

    case: auto|cantilever|solid|bcc|fcc|engine_mount|
          brake_pedal|brake_solid|brake_bcc|brake_fcc|brake_pedal_solid|...
    """
    settings = get_settings()
    key = (case or "auto").lower().strip()
    mapping = {
        "cantilever": "cantilever_precomputed.json",
        "solid": em.precomputed_filename("solid"),
        "bcc": em.precomputed_filename("bcc"),
        "fcc": em.precomputed_filename("fcc"),
        "engine_mount": em.precomputed_filename("bcc"),
        "brake_pedal": bp.precomputed_filename("xtruss"),
        "brake_solid": bp.precomputed_filename("solid"),
        "brake_bcc": bp.precomputed_filename("xtruss"),
        "brake_xtruss": bp.precomputed_filename("xtruss"),
        "brake_fcc": bp.precomputed_filename("fcc"),
        "brake_pedal_solid": bp.precomputed_filename("solid"),
        "brake_pedal_bcc": bp.precomputed_filename("xtruss"),
        "brake_pedal_xtruss": bp.precomputed_filename("xtruss"),
        "brake_pedal_fcc": bp.precomputed_filename("fcc"),
    }
    if key == "auto":
        geo = _STATE.get("geometry") or {}
        res = _STATE.get("results") or {}
        if geo.get("part") == "brake_pedal" or res.get("part") == "brake_pedal":
            wt = bp.normalize_web_type(str(geo.get("web_type") or res.get("web_type") or "xtruss"))
            key = f"brake_{wt}" if wt in bp.WEB_TYPES else "brake_xtruss"
        elif geo.get("part") == "engine_mount":
            key = str(geo.get("web_type") or "bcc")
        elif res.get("part") == "engine_mount":
            key = str(res.get("web_type") or "bcc")
        else:
            if (settings.results_dir / bp.precomputed_filename("xtruss")).exists():
                key = "brake_xtruss"
            elif (settings.results_dir / em.precomputed_filename("bcc")).exists():
                key = "bcc"
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
    if key in brake_keys:
        if key == "brake_pedal":
            wt = "xtruss"
        elif key.startswith("brake_pedal_"):
            wt = key.replace("brake_pedal_", "")
        else:
            wt = key.replace("brake_", "")
        fname = bp.precomputed_filename(bp.normalize_web_type(wt))
    elif key in em.WEB_TYPES:
        fname = em.precomputed_filename(key)
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
        elif key in em.WEB_TYPES or key in ("engine_mount", "auto"):
            wt = key if key in em.WEB_TYPES else "bcc"
            data = em.fallback_fea_result(wt, em.DEFAULT_FORCE_N)
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
    elif data.get("part") == "engine_mount":
        _STATE["geometry"] = {
            **(
                em.memory_geometry(
                    str(data.get("web_type", "bcc")),
                    float(data.get("cell_size_mm", em.DEFAULT_CELL_SIZE_MM)),
                    float(data.get("strut_radius_mm", em.DEFAULT_STRUT_RADIUS_MM)),
                    "Loaded from precomputed results.",
                )
            ),
            **{
                k: data.get(k)
                for k in ("volume_mm3", "mass_kg", "relative_density")
                if data.get(k) is not None
            },
            "part": "engine_mount",
            "web_type": data.get("web_type"),
        }
    return {"ok": True, "results": data, "path": str(path), "case": key}


TOOL_SPECS = [
    {
        "name": "create_brake_pedal",
        "description": (
            "Create an Al brake-pedal lattice bracket (pivot + clevis rings + footpad) "
            "with web_type solid|xtruss|fcc lattice fill, export STEP/STL, open FreeCAD GUI."
        ),
        "parameters": {
            "web_type": "solid|xtruss|fcc, default xtruss (bcc aliases to xtruss)",
            "cell_size_mm": "float, default 15",
            "strut_radius_mm": "float, default 2.5 (xtruss strut thickness / fcc radius)",
            "open_gui": "bool, default true",
        },
    },
    {
        "name": "create_engine_mount",
        "description": (
            "Create a simplified Al engine-mount L-bracket (solid bolt flange + load pad) "
            "with web_type solid|bcc|fcc lattice fill, export STEP/STL, open FreeCAD GUI."
        ),
        "parameters": {
            "web_type": "solid|bcc|fcc, default bcc",
            "cell_size_mm": "float, default 15",
            "strut_radius_mm": "float, default 2.2 (needed for meshable BCC)",
            "open_gui": "bool, default true",
        },
    },
    {
        "name": "get_lattice_metrics",
        "description": (
            "Return relative density, volumes, and mass estimate for the current "
            "brake-pedal or engine-mount geometry."
        ),
        "parameters": {},
    },
    {
        "name": "compare_brake_pedal_variants",
        "description": (
            "Compare solid vs X-truss vs FCC brake-pedal mass, relative density, "
            "max von Mises, pad deflection; recommend lightest with SF>=1.5."
        ),
        "parameters": {},
    },
    {
        "name": "compare_mount_variants",
        "description": (
            "Compare solid vs BCC vs FCC engine-mount mass, relative density, "
            "max von Mises, pad deflection; recommend lightest with SF>=1.5."
        ),
        "parameters": {},
    },
    {
        "name": "create_cantilever",
        "description": (
            "Create a rectangular cantilever beam (mm), export STEP/STL, "
            "and open the model in the FreeCAD GUI."
        ),
        "parameters": {
            "length_mm": "float, default 100",
            "width_mm": "float, default 20",
            "height_mm": "float, default 5",
            "open_gui": "bool, default true",
        },
    },
    {
        "name": "apply_load_and_solve",
        "description": (
            "Apply load (N), mesh with Gmsh, solve with CalculiX inside FreeCAD "
            "(brake-pedal footpad, engine-mount pad, or cantilever tip), save results, "
            "open GUI. Requires create_brake_pedal, create_engine_mount, or "
            "create_cantilever first."
        ),
        "parameters": {
            "force_n": "float, default 500 brake pedal / 20000 mount / 100 cantilever",
            "mesh_max_size_mm": "float, default 5 (pedal) / 4 (mount) / 2.5 (cantilever)",
            "open_gui": "bool, default true",
        },
    },
    {
        "name": "get_max_von_mises",
        "description": "Return max von Mises stress (MPa) from the latest solve.",
        "parameters": {},
    },
    {
        "name": "open_in_freecad",
        "description": "Launch FreeCAD GUI with the latest CAD/FEM document.",
        "parameters": {},
    },
]


def call_tool(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {}
    if name == "create_brake_pedal":
        return create_brake_pedal(
            web_type=str(args.get("web_type", "xtruss")),
            cell_size_mm=float(args.get("cell_size_mm", bp.DEFAULT_CELL_SIZE_MM)),
            strut_radius_mm=float(
                args.get("strut_radius_mm", bp.DEFAULT_STRUT_RADIUS_MM)
            ),
            open_gui=bool(args.get("open_gui", True)),
        )
    if name == "create_engine_mount":
        return create_engine_mount(
            web_type=str(args.get("web_type", "bcc")),
            cell_size_mm=float(args.get("cell_size_mm", em.DEFAULT_CELL_SIZE_MM)),
            strut_radius_mm=float(
                args.get("strut_radius_mm", em.DEFAULT_STRUT_RADIUS_MM)
            ),
            open_gui=bool(args.get("open_gui", True)),
        )
    if name == "get_lattice_metrics":
        return get_lattice_metrics()
    if name == "compare_brake_pedal_variants":
        return compare_brake_pedal_variants()
    if name == "compare_mount_variants":
        return compare_mount_variants()
    if name == "create_cantilever":
        return create_cantilever(
            length_mm=float(args.get("length_mm", 100)),
            width_mm=float(args.get("width_mm", 20)),
            height_mm=float(args.get("height_mm", 5)),
            open_gui=bool(args.get("open_gui", True)),
        )
    if name == "apply_load_and_solve":
        force = args.get("force_n")
        mesh = args.get("mesh_max_size_mm")
        return apply_load_and_solve(
            force_n=float(force) if force is not None else None,
            mesh_max_size_mm=float(mesh) if mesh is not None else None,
            open_gui=bool(args.get("open_gui", True)),
        )
    if name == "get_max_von_mises":
        return get_max_von_mises()
    if name == "open_in_freecad":
        return open_current_in_freecad()
    return {"ok": False, "error": f"Unknown tool: {name}"}
