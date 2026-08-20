"""F08 mesh convergence study: refine-and-compare over live CalculiX solves.

Rules (ADR-009):

- Live solves only. The study refuses setups whose "solve" does not vary
  with mesh size (fcc pedal = precomputed demo KPIs; FreeCAD absent =
  analytical fallback) — a convergence table of canned numbers would be
  theater, not verification.
- Metric: max von Mises (primary); pad/tip deflection rides along as context.
  Recommendation = the coarsest mesh whose max von Mises sits within
  ``CONVERGENCE_TOLERANCE`` (5%) of the finest run's value — the cheapest
  mesh that buys the converged answer. If no coarser mesh qualifies, the
  study reports not-converged and offers the finest mesh as best-available
  with a refine-further flag instead of pretending.
- Mesh ladder: fixed multipliers of the part's default mesh (1.0 / 0.7 /
  0.5 — e.g. pedal 5 / 3.5 / 2.5 mm); an explicit ``mesh_sizes_mm`` list
  (2-4 entries) overrides it. Geometry-aware ladders wait for F26.
- Synchronous by design (async handles are F11): sub-runs are forced to
  ``open_gui=False`` and go through ``apply_load_and_solve``, so each is an
  ordinary F06 run-history record and the report cites its ``run_id``. A
  failed or fallen-back mesh is reported, never hidden — the study flags
  itself ``incomplete`` instead of aborting silently. The session ends on
  the finest run's result, exactly as if the solves had been issued by hand.
"""

from __future__ import annotations

import math
from typing import Any

from companion.tools import brake_pedal as bp
from companion.tools import outcome
from companion.tools import uav_arm as ua
from companion.tools.freecad_runtime import find_freecad_cmd

MESH_MULTIPLIERS = (1.0, 0.7, 0.5)
CONVERGENCE_TOLERANCE = 0.05
LIVE_METHOD = "calculix_ccx"
CANTILEVER_DEFAULT_MESH_MM = 2.5
CANTILEVER_DEFAULT_FORCE_N = 100.0


def default_mesh_mm(part: str) -> float:
    if part == "brake_pedal":
        return bp.DEFAULT_MESH_MM
    if part == "uav_arm":
        return ua.DEFAULT_MESH_MM
    return CANTILEVER_DEFAULT_MESH_MM


def default_force_n(part: str) -> float:
    if part == "brake_pedal":
        return bp.DEFAULT_FORCE_N
    if part == "uav_arm":
        return ua.DEFAULT_FORCE_N
    return CANTILEVER_DEFAULT_FORCE_N


def mesh_ladder(baseline_mm: float) -> list[float]:
    """Default ladder: multipliers of the baseline, coarse -> fine, deduped."""
    sizes = {
        round(float(baseline_mm) * mult, 3) for mult in MESH_MULTIPLIERS
    }
    return sorted(sizes, reverse=True)


def validate_mesh_sizes(mesh_sizes_mm: Any) -> tuple[list[float] | None, dict | None]:
    """Normalize an explicit mesh list; (None, failure) on bad input."""
    if mesh_sizes_mm is None:
        return None, None
    if not isinstance(mesh_sizes_mm, (list, tuple)):
        return None, _bad_mesh_sizes(
            f"mesh_sizes_mm must be a list of 2-4 mesh sizes in mm, "
            f"got {type(mesh_sizes_mm).__name__}"
        )
    try:
        sizes = [float(size) for size in mesh_sizes_mm]
    except (TypeError, ValueError):
        return None, _bad_mesh_sizes("mesh_sizes_mm entries must be numbers (mm)")
    if not 2 <= len(sizes) <= 4:
        return None, _bad_mesh_sizes(
            f"mesh_sizes_mm needs 2-4 entries, got {len(sizes)}"
        )
    if any(not math.isfinite(size) or not (size > 0.0) for size in sizes):
        return None, _bad_mesh_sizes("mesh_sizes_mm entries must be positive finite mm")
    unique = sorted({round(size, 3) for size in sizes}, reverse=True)
    if len(unique) < 2:
        return None, _bad_mesh_sizes("mesh_sizes_mm entries must differ (got duplicates)")
    return unique, None


def _bad_mesh_sizes(error: str) -> dict:
    return {
        "ok": False,
        "error": error,
        "error_class": "bad_params",
        "correction": (
            "Pass mesh_sizes_mm as 2-4 distinct positive sizes in mm, "
            "e.g. [6, 4, 3], or omit it for the default multiplier ladder."
        ),
    }


def _first_not_none(source: dict, *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None:
            return value
    return None


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(number) and number > 0.0:
        return number
    return None


def run_convergence_study(
    mesh_sizes_mm: Any = None,
    force_n: float | None = None,
) -> dict:
    """Solve the active part at 2-4 mesh sizes; recommend the coarsest
    converged one. See the module docstring for the contract."""
    # Lazy import: cad_fea's dispatcher imports this module lazily too, and
    # the call-time attribute lookup keeps tests able to stub the solver.
    from companion.tools import cad_fea

    geometry = cad_fea.get_state().get("geometry")
    if not geometry:
        return {
            "ok": False,
            "error": (
                "No geometry. Call create_brake_pedal, "
                "create_uav_arm, or create_cantilever first."
            ),
            "error_class": "no_geometry",
            "correction": (
                "Call create_brake_pedal, create_uav_arm, or "
                "create_cantilever first, "
                "then re-run the convergence study."
            ),
        }
    part = str(geometry.get("part") or "")
    web_type = str(geometry.get("web_type") or "") or None
    if part == "brake_pedal" and bp.normalize_web_type(web_type or "xtruss") == "fcc":
        return {
            "ok": False,
            "error": (
                "FCC pedal solves return precomputed demo KPIs that do not "
                "vary with mesh size; a convergence study needs live "
                "CalculiX solves."
            ),
            "error_class": "unsupported_setup",
            "correction": (
                "Switch to web_type xtruss or solid "
                "(update_design_program), then re-run the convergence study."
            ),
        }
    if not find_freecad_cmd():
        return {
            "ok": False,
            "error": (
                "FreeCAD not installed; the convergence study needs live "
                "CalculiX solves, not the analytical fallback."
            ),
            "error_class": "freecad_missing",
            "correction": (
                "Install FreeCAD (or point FREECAD_CMD at FreeCADCmd), "
                "then re-run the convergence study."
            ),
        }

    sizes, failure = validate_mesh_sizes(mesh_sizes_mm)
    if failure:
        return failure
    ladder = sizes or mesh_ladder(default_mesh_mm(part))

    rows: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    force_used: float | None = force_n
    for size in ladder:
        result = cad_fea.apply_load_and_solve(
            force_n=force_n, mesh_max_size_mm=size, open_gui=False
        )
        if result.get("force_n") is not None:
            force_used = result.get("force_n")
        vm = _finite_positive(result.get("max_von_mises_mpa")) if result.get("ok") else None
        live = (
            result.get("method") == LIVE_METHOD and not result.get("fallback")
        )
        if vm is None or not live:
            raw_error = result.get("error") or (
                f"solve returned method {result.get('method')!r} "
                "(not a live CalculiX solve)"
            )
            failed.append(
                {
                    "mesh_max_size_mm": size,
                    "error": outcome.condense_error(str(raw_error)),
                    "error_class": result.get("error_class")
                    or outcome.classify_error(str(raw_error)),
                }
            )
            continue
        rows.append(
            {
                "mesh_max_size_mm": size,
                "node_count": result.get("node_count"),
                "max_von_mises_mpa": result.get("max_von_mises_mpa"),
                "deflection_mm": _first_not_none(
                    result, "pad_deflection_mm", "tip_deflection_mm"
                ),
                "run_id": result.get("run_id"),
            }
        )

    if not rows:
        last = failed[-1]
        return {
            "ok": False,
            "error": (
                f"All {len(ladder)} mesh sizes failed to produce a live "
                f"solve; last error at {last['mesh_max_size_mm']} mm: "
                f"{last['error']}"
            ),
            "error_class": last["error_class"],
        }

    converged, recommended, verdict_note = _verdict(rows)
    for index, row in enumerate(rows):
        row["pct_change_vs_coarser"] = (
            None if index == 0 else _pct_change(row, rows[index - 1])
        )

    finest = rows[-1]
    report: dict[str, Any] = {
        "ok": True,
        "part": part,
        "web_type": web_type,
        "force_n": force_used if force_used is not None else default_force_n(part),
        "metric": "max_von_mises_mpa",
        "tolerance_pct": round(CONVERGENCE_TOLERANCE * 100, 1),
        "runs": rows,
        "failed_meshes": failed,
        "incomplete": bool(failed),
        "converged": converged,
        "recommended_mesh_max_size_mm": recommended,
        "verdict": verdict_note,
        "note": (
            f"{len(rows)} live CalculiX solves at mesh sizes "
            f"{[row['mesh_max_size_mm'] for row in rows]} mm; each sub-run is "
            "a run-history record (run_id cited above). Recommendation = "
            "coarsest mesh within "
            f"{round(CONVERGENCE_TOLERANCE * 100, 1)}% of the finest max von "
            f"Mises ({finest['max_von_mises_mpa']} MPa at "
            f"{finest['mesh_max_size_mm']} mm). Method: calculix_ccx "
            "(Gmsh tets). Not verified: local refinement around the stress "
            "peak; deflection is context, not the convergence metric."
        ),
    }
    return report


def _pct_change(row: dict[str, Any], coarser: dict[str, Any]) -> float | None:
    finer = _finite_positive(row.get("max_von_mises_mpa"))
    coarse = _finite_positive(coarser.get("max_von_mises_mpa"))
    if finer is None or coarse is None:
        return None
    return round(abs(finer - coarse) / finer * 100.0, 2)


def _verdict(rows: list[dict[str, Any]]) -> tuple[bool | None, float | None, str]:
    """(converged, recommended mesh, verdict text) over coarse->fine rows."""
    if len(rows) < 2:
        return None, None, (
            "incomplete: fewer than two meshes solved, no convergence verdict"
        )
    finest = rows[-1]
    finest_vm = _finite_positive(finest.get("max_von_mises_mpa"))
    if finest_vm is None:
        return None, None, "no verdict: finest run has no usable max von Mises"
    for row in rows[:-1]:
        vm = _finite_positive(row.get("max_von_mises_mpa"))
        if vm is None:
            continue
        if abs(vm - finest_vm) / finest_vm <= CONVERGENCE_TOLERANCE:
            return (
                True,
                row["mesh_max_size_mm"],
                (
                    f"converged: {row['mesh_max_size_mm']} mm agrees with the "
                    f"finest run within {round(CONVERGENCE_TOLERANCE * 100, 1)}% "
                    f"({vm} vs {finest_vm} MPa) and is the cheapest such mesh"
                ),
            )
    return (
        False,
        finest["mesh_max_size_mm"],
        (
            "not converged: no coarser mesh agrees with the finest run within "
            f"{round(CONVERGENCE_TOLERANCE * 100, 1)}% — refine further before "
            "trusting the peak stress"
        ),
    )
