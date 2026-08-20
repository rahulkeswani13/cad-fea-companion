"""F03 pre-mesh B-Rep validation gate.

Two layers:

- Host-side `validate_geometry_payload(params)` — rejects degenerate parameter
  values (<= 0, NaN, non-numeric) before FreeCADCmd is ever launched, and is
  deterministic + memory-testable.
- FreeCAD-side `FREECAD_VALIDATION_SNIPPET` — injected into the generator
  geometry/FEM scripts; checks the built B-Rep (isValid, volume, bbox) right
  after the shape exists and BEFORE any STEP/STL export or Gmsh meshing. A
  failed check early-prints the COMPANION_JSON failure payload with a named
  stage and exits before mesh/solve.

Hard checks block: shape_null, brep_invalid, volume_nonpositive,
bbox_degenerate. Plausibility checks only warn (measured volume vs the host
estimate, relative-density bounds) so boolean fuzz can never block a demo.
Failures surface through the F02 envelope as error_class `geometry_invalid`
with the stage in `validation.stage`.
"""

from __future__ import annotations

from typing import Any

STAGE_PASSED = "passed"
STAGE_PARAMS_NONPOSITIVE = "params_nonpositive"
STAGE_SHAPE_NULL = "shape_null"
STAGE_BREP_INVALID = "brep_invalid"
STAGE_VOLUME_NONPOSITIVE = "volume_nonpositive"
STAGE_BBOX_DEGENERATE = "bbox_degenerate"

HARD_STAGES = (
    STAGE_PARAMS_NONPOSITIVE,
    STAGE_SHAPE_NULL,
    STAGE_BREP_INVALID,
    STAGE_VOLUME_NONPOSITIVE,
    STAGE_BBOX_DEGENERATE,
)


def validate_geometry_payload(params: dict[str, Any]) -> dict[str, Any] | None:
    """Host-side degenerate-param gate. Returns a failure payload or None.

    `not (value > 0)` also catches NaN (all NaN comparisons are False).
    """
    bad: dict[str, Any] = {}
    for name, value in params.items():
        try:
            finite_positive = float(value) > 0.0
        except (TypeError, ValueError):
            finite_positive = False
        if not finite_positive:
            bad[name] = value
    if not bad:
        return None
    return {
        "ok": False,
        "error": (
            "geometry validation failed at stage params_nonpositive: "
            f"{', '.join(f'{k} must be > 0, got {v!r}' for k, v in bad.items())}"
        ),
        "error_class": "geometry_invalid",
        "validation": {
            "stage": STAGE_PARAMS_NONPOSITIVE,
            "checks": bad,
            "warnings": [],
        },
    }


# Injected verbatim into FreeCAD generator scripts (plain string — no format
# placeholders). Robust against null shapes: measurement errors classify as
# brep_invalid rather than crashing the script.
FREECAD_VALIDATION_SNIPPET = '''

def companion_validate_brep(body, expected_vol_mm3=None, relative_density=None, expected_bbox_mm=None):
    """F03 pre-mesh B-Rep gate. Returns (stage, checks, warnings)."""
    checks = {}
    warnings = []
    if body is None:
        checks["shape_nonnull"] = False
        return "shape_null", checks, warnings
    checks["shape_nonnull"] = True
    try:
        checks["is_valid"] = bool(body.isValid())
    except Exception as exc:
        checks["is_valid"] = False
        checks["is_valid_error"] = "%s: %s" % (type(exc).__name__, exc)
    try:
        vol = float(body.Volume)
        bb = body.BoundBox
        dims = (bb.XLength, bb.YLength, bb.ZLength)
    except Exception as exc:
        checks["measure_error"] = "%s: %s" % (type(exc).__name__, exc)
        return "brep_invalid", checks, warnings
    checks["volume_mm3"] = vol
    checks["bbox_mm"] = {
        "x": [bb.XMin, bb.XMax],
        "y": [bb.YMin, bb.YMax],
        "z": [bb.ZMin, bb.ZMax],
    }
    checks["bbox_dims_mm"] = [round(d, 4) for d in dims]
    if not checks["is_valid"]:
        return "brep_invalid", checks, warnings
    if not (vol > 0.0):
        return "volume_nonpositive", checks, warnings
    if not all(d > 1e-6 for d in dims):
        return "bbox_degenerate", checks, warnings
    if expected_vol_mm3:
        ratio = vol / float(expected_vol_mm3)
        checks["volume_vs_estimate"] = round(ratio, 4)
        if not 0.5 <= ratio <= 1.5:
            warnings.append("volume_implausible")
    if relative_density is not None:
        checks["relative_density"] = float(relative_density)
        if not 0.0 < float(relative_density) <= 1.05:
            warnings.append("relative_density_implausible")
    if expected_bbox_mm:
        # text-to-cad plan-first rule: declared expected bounding box vs the
        # built B-Rep. Warn-only (25%) — scaling a design must never hard-fail.
        got = checks["bbox_dims_mm"]
        if len(got) == 3:
            dev = 0.0
            for measured, wanted in zip(got, expected_bbox_mm):
                wanted = float(wanted)
                if wanted > 0.0:
                    dev = max(dev, abs(measured - wanted) / wanted)
            checks["bbox_vs_expected_max_dev"] = round(dev, 4)
            if dev > 0.25:
                warnings.append("bbox_implausible")
    return "passed", checks, warnings


def companion_gate_payload(part, stage, checks, warnings):
    return {
        "ok": False,
        "error": "geometry validation failed at stage %s (part=%s)"
        % (stage, part),
        "error_class": "geometry_invalid",
        "validation": {"stage": stage, "checks": checks, "warnings": warnings},
    }
'''


def gate_call_snippet(
    part: str, expected_vol_mm3: float, expected_bbox_mm: list[float] | None = None
) -> str:
    """Gate invocation block for generator scripts (4-space indent, inside try).

    Sits after the body is built and recomputed; a failed stage prints the
    COMPANION_JSON failure payload and exits before export/mesh/solve.
    SystemExit is a BaseException, so the script's `except Exception` does not
    swallow it. ``expected_bbox_mm`` (additive, optional) adds the plan-first
    bbox warn-check.
    """
    bbox_arg = (
        ", expected_bbox_mm=%r" % [float(d) for d in expected_bbox_mm]
        if expected_bbox_mm
        else ""
    )
    return f'''
    # F03 pre-export/pre-mesh B-Rep validation gate
    _vstage, _vchecks, _vwarn = companion_validate_brep(
        body, {float(expected_vol_mm3)}, (rho if web_type != "solid" else None){bbox_arg}
    )
    if _vstage != "passed":
        print(
            "COMPANION_JSON:"
            + json.dumps(companion_gate_payload("{part}", _vstage, _vchecks, _vwarn))
        )
        # FreeCADCmd's embedded interpreter can drop buffered stdout on
        # SystemExit — flush so the marker always reaches the host parser.
        import sys as _sys

        _sys.stdout.flush()
        raise SystemExit(0)
    validation = {{"stage": _vstage, "checks": _vchecks, "warnings": _vwarn}}
'''
