"""F04 design program layer.

A design program is the persisted, editable source of truth for a parametric
part: ``data/workspace/<part>_program.json`` holds the editable params, the
read-only fixed constants, a monotonic ``rev``, and a ``params_hash`` (sha256
over canonical JSON of the params). Generated geometry is derived from it.

Rules (ADR-004):

- Preflight hard-rejects out-of-range values with one concrete correction
  naming the valid range — never clamps (solver honesty).
- The file is committed only after a successful rebuild (write-tmp + rename);
  a failed rebuild leaves the accepted revision untouched on disk.
- No history array: the file holds the current accepted program only.
- No file locking: single-writer (one agent session) is a documented limit.
- Analysis params (force, mesh, BCs) are NOT program params — F10 adds them.
- ``material`` IS an editable program param (F09, ADR-010): enum-validated
  against ``data/materials.json`` like ``web_type``, not a numeric range. The
  cantilever's pre-F09 read-only ``material`` fixed constant became editable;
  per-part defaults (al6061t6 / steel) keep old callers byte-identical.
- Export/result filenames are not revision-tagged; ``rev``/``params_hash``
  ride inside result payloads (per-run artifacts are F06's job).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from companion.config import get_settings
from companion.tools import brake_pedal as bp
from companion.tools import materials as mats
from companion.tools import uav_arm as ua
from companion.tools.tool_schemas import numeric_param_ranges

KNOWN_PARTS = ("brake_pedal", "cantilever", "uav_arm")

# H3: derived view of the canonical pydantic arg models — the same ge/le
# constraints that boundary-reject tool calls define the program floors, so
# the two can never drift. Public API (shape + values) unchanged.
PARAM_SPECS: dict[str, dict[str, tuple[float, float]]] = numeric_param_ranges()

WEB_TYPES: dict[str, frozenset[str]] = {
    "brake_pedal": bp.WEB_TYPES,  # solid | xtruss | fcc
    "uav_arm": ua.WEB_TYPES,  # solid | xtruss (fcc additive later)
}

# Read-only constants listed for completeness (a program is a full description
# of the part; sending these in `changes` is rejected). Derived from the
# generator modules so the listing cannot drift from the scripts.
FIXED_CONSTANTS: dict[str, dict[str, Any]] = {
    "brake_pedal": {
        "thickness_z_mm": bp.THICKNESS_Z,
        "pivot_xy_mm": list(bp.PIVOT_XY),
        "clevis_xy_mm": list(bp.CLEVIS_XY),
        "footpad_xy_mm": [bp.FOOTPAD_X, bp.FOOTPAD_Y],
        "rim_mm": bp.RIM_MM,
        "fillet_mm": bp.FILLET_MM,
    },
    "cantilever": {},
    "uav_arm": {
        "boss_lx_mm": ua.BOSS_LX,
        "boss_ly_mm": ua.BOSS_LY,
        "boss_lz_mm": ua.BOSS_LZ,
        "arm_root_w_mm": ua.ARM_ROOT_W,
        "arm_root_h_mm": ua.ARM_ROOT_H,
        "arm_tip_w_mm": ua.ARM_TIP_W,
        "arm_tip_h_mm": ua.ARM_TIP_H,
        "ring_od_mm": 2.0 * ua.RING_OR,
        "ring_id_mm": 2.0 * ua.RING_IR,
        "ring_t_mm": ua.RING_T,
        "chord_t_mm": ua.CHORD_T_MM,
    },
}


def default_params(part: str) -> dict[str, Any]:
    """Editable params matching the create_* tool defaults for `part`."""
    if part == "brake_pedal":
        return {
            "web_type": "xtruss",
            "cell_size_mm": bp.DEFAULT_CELL_SIZE_MM,
            "strut_radius_mm": bp.DEFAULT_STRUT_RADIUS_MM,
            "material": mats.DEFAULT_PART_MATERIAL["brake_pedal"],
        }
    if part == "cantilever":
        return {
            "length_mm": 100.0,
            "width_mm": 20.0,
            "height_mm": 5.0,
            "material": mats.DEFAULT_PART_MATERIAL["cantilever"],
        }
    if part == "uav_arm":
        return {
            "web_type": "solid",
            "arm_length_mm": ua.ARM_LENGTH_MM,
            "cell_size_mm": ua.DEFAULT_CELL_SIZE_MM,
            "strut_radius_mm": ua.DEFAULT_STRUT_RADIUS_MM,
            "material": mats.DEFAULT_PART_MATERIAL["uav_arm"],
        }
    raise KeyError(part)


def editable_params(part: str) -> list[str]:
    names = list(PARAM_SPECS.get(part, {}))
    if part in WEB_TYPES:
        names.insert(0, "web_type")
    names.append("material")
    return names


def params_hash(params: dict[str, Any]) -> str:
    """Stable identity of a param set (sha256 over canonical JSON, 12 hex).

    Numbers are coerced to float before hashing so `12` (fresh from an LLM
    tool call) and `12.0` (round-tripped from the program file) are the same
    design.
    """
    canonical = {
        key: float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value
        for key, value in params.items()
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def program_path(part: str) -> Path:
    return get_settings().workspace_dir / f"{part}_program.json"


def load_program(part: str) -> dict[str, Any] | None:
    path = program_path(part)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("part") == part else None


def save_program(part: str, params: dict[str, Any], prev_rev: int | None) -> dict[str, Any]:
    """Commit the accepted program: tmp write + rename so a partial write can
    never clobber the previous revision."""
    program = {
        "part": part,
        "rev": int(prev_rev or 0) + 1,
        "params_hash": params_hash(params),
        "params": params,
        "fixed": FIXED_CONSTANTS[part],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    path = program_path(part)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(program, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return program


def list_programs() -> list[dict[str, Any]]:
    """Compact inventory of on-disk programs (part, rev, params_hash)."""
    out: list[dict[str, Any]] = []
    for path in sorted(get_settings().workspace_dir.glob("*_program.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("part"):
            out.append(
                {
                    "part": data.get("part"),
                    "rev": data.get("rev"),
                    "params_hash": data.get("params_hash"),
                }
            )
    return out


def _bad_params(message: str, correction: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "ok": False,
        "error": message,
        "error_class": "bad_params",
        "correction": correction,
    }
    if extra:
        payload.update(extra)
    return payload


def normalize_changes(
    part: str, changes: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Validate change keys and coerce values (web_type aliases -> canonical).

    Returns (normalized, None) or (None, failure payload). Numeric params are
    coerced to float here; range enforcement happens in preflight.
    """
    if not isinstance(changes, dict):
        return None, _bad_params(
            "changes must be an object mapping parameter names to values, "
            f"got {type(changes).__name__}",
            "Pass changes as an object, e.g. {\"cell_size_mm\": 12}.",
        )
    editable = editable_params(part)
    fixed = FIXED_CONSTANTS.get(part, {})
    normalized: dict[str, Any] = {}
    bad: dict[str, Any] = {}
    for key, value in changes.items():
        if key in fixed:
            bad[key] = value
            continue
        if key == "web_type":
            raw = str(value or "").lower().strip().replace("-", "_")
            if part == "brake_pedal":
                raw = bp.normalize_web_type(raw)
            elif part == "uav_arm":
                raw = ua.normalize_web_type(raw)
            if raw not in WEB_TYPES.get(part, frozenset()):
                bad[key] = value
                continue
            normalized[key] = raw
            continue
        if key == "material":
            record = mats.get_material(value)
            if record is None:
                bad[key] = value
                continue
            normalized[key] = record["id"]
            continue
        if key not in PARAM_SPECS[part]:
            bad[key] = value
            continue
        try:
            normalized[key] = float(value)
        except (TypeError, ValueError):
            bad[key] = value
    if bad:
        reasons = []
        for key, value in bad.items():
            if key in fixed:
                reasons.append(
                    f"{key}={value!r} is a fixed constant of {part} (read-only)"
                )
            elif key == "material":
                reasons.append(
                    f"material={value!r} is not a known material; valid ids: "
                    f"{mats.material_ids()}"
                )
            elif key == "web_type" or key not in PARAM_SPECS[part]:
                reasons.append(
                    f"{key}={value!r} is not an editable parameter of {part}"
                    + (
                        f" (web_type must be one of {sorted(WEB_TYPES[part])})"
                        if key == "web_type"
                        else ""
                    )
                )
            else:
                reasons.append(f"{key}={value!r} is not a number")
        return None, _bad_params(
            f"design program update rejected for {part}: " + "; ".join(reasons),
            f"Use only editable parameters of {part}: "
            f"{', '.join(editable)}. Fixed constants cannot be edited.",
            {"preflight": {"part": part, "violations": bad}},
        )
    return normalized, None


def preflight(part: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Range-check a full param set. Returns a failure payload or None.

    Hard reject with the valid range named — never clamp. `not (lo <= v <= hi)`
    also catches NaN (all NaN comparisons are False).
    """
    violations: dict[str, Any] = {}
    for name, (lo, hi) in PARAM_SPECS[part].items():
        value = params.get(name)
        try:
            num = float(value)
        except (TypeError, ValueError):
            num = math.nan
        if not (lo <= num <= hi) or math.isnan(num):
            violations[name] = value
    if not violations:
        return None
    reasons = "; ".join(
        f"{name} must be within [{PARAM_SPECS[part][name][0]}, "
        f"{PARAM_SPECS[part][name][1]}], got {violations[name]!r}"
        for name in violations
    )
    fixes = "; ".join(
        f"set {name} between {PARAM_SPECS[part][name][0]} and "
        f"{PARAM_SPECS[part][name][1]}"
        for name in violations
    )
    return _bad_params(
        f"design program preflight failed for {part}: {reasons}",
        f"{fixes}, then retry update_design_program.",
        {"preflight": {"part": part, "violations": violations}},
    )
