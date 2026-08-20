"""F09 material table: cited properties, alias resolution, physics scaling.

Source of truth is ``data/materials.json`` (ADR-010); ``docs/materials.md``
mirrors it so the RAG store can cite the same numbers, and
``tests/test_materials.py`` asserts the two stay in sync.

Scaling model for ``compare_materials`` (one live/precomputed solve in the
reference material, then linear-elastic bookkeeping):

- stress is unchanged (load-driven linear elasticity; the lattice is not
  perfectly statically determinate, so this is an assumption we state),
- deflection scales by E_ref/E_new,
- mass scales by rho_new/rho_ref,
- safety factor = yield_new / vm.

Every scaled row carries a method label (``scaled_from_calculix`` or
``<base_method>_scaled``) and a not-verified note. PA12 deflection is flagged
separately: at E~1.8 GPa the linear scaling leaves the small-strain regime.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from companion.config import get_settings

SF_THRESHOLD = 1.5

# Per-part default material ids (preserve pre-F09 behavior exactly).
DEFAULT_PART_MATERIAL: dict[str, str] = {
    "brake_pedal": "al6061t6",
    "cantilever": "steel",
    "uav_arm": "al6061t6",
}

_TABLE: dict[str, dict[str, Any]] | None = None


def materials_path() -> Path:
    return get_settings().data_dir / "materials.json"


def load_materials() -> dict[str, dict[str, Any]]:
    """Material records keyed by canonical id (cached per process)."""
    global _TABLE
    if _TABLE is None:
        raw = json.loads(materials_path().read_text(encoding="utf-8"))
        _TABLE = {str(m["id"]): m for m in raw["materials"]}
    return _TABLE


def reset_cache() -> None:
    """Test hook: force a re-read of data/materials.json."""
    global _TABLE
    _TABLE = None


def material_ids() -> list[str]:
    return list(load_materials())


def normalize_key(raw: Any) -> str:
    """'Ti-6Al-4V' -> 'ti6al4v'; 'Al 6061-T6' -> 'al6061t6'."""
    return re.sub(r"[^a-z0-9]", "", str(raw or "").lower())


def get_material(raw: Any) -> dict[str, Any] | None:
    """Resolve user input / stored id / display name to a full record."""
    key = normalize_key(raw)
    if not key:
        return None
    table = load_materials()
    if key in table:
        return dict(table[key])
    for record in table.values():
        if key in {normalize_key(a) for a in record.get("aliases", [])}:
            return dict(record)
        if key == normalize_key(record.get("display_name")):
            return dict(record)
    return None


def material_for_part(part: str | None) -> dict[str, Any]:
    """Default record for a part (never None — falls back to the table)."""
    mat_id = DEFAULT_PART_MATERIAL.get(str(part or ""), "al6061t6")
    return dict(load_materials().get(mat_id) or load_materials()["al6061t6"])


def describe(record: dict[str, Any] | None) -> str:
    """Legacy one-line material string kept by pre-F09 result payloads.

    Default Al is byte-identical to the old hardcoded string.
    """
    if not record:
        return "Al 6061-T6 approx E=69 GPa, nu=0.33"
    e_gpa = float(record["youngs_modulus_mpa"]) / 1000.0
    nu = float(record["poissons_ratio"])
    nu_txt = ("%g" % nu)
    return f"{record['display_name']} approx E={e_gpa:g} GPa, nu={nu_txt}"


def resolve_result_material(
    result: dict[str, Any] | None, part: str | None = None
) -> dict[str, Any]:
    """Material record for a stored/legacy result payload.

    Prefers ``material_id`` (F09 results); legacy payloads carry a free-text
    ``material`` string like 'Al 6061-T6 approx E=69 GPa...' — matched by
    normalized prefix, else the part default.
    """
    result = result or {}
    mat = get_material(result.get("material_id"))
    if mat:
        return mat
    text = str(result.get("material") or "")
    if text:
        head = text.split("approx")[0].strip()
        mat = get_material(head)
        if mat:
            return mat
    return material_for_part(part)


def bad_material_payload(raw: Any, context: str = "") -> dict[str, Any]:
    """One error + one concrete correction naming the valid materials."""
    names = "; ".join(
        f"{m['display_name']} (\"{m['id']}\")" for m in load_materials().values()
    )
    return {
        "ok": False,
        "error": (
            f"unknown material {raw!r}{f' {context}' if context else ''}; "
            f"known materials: {names}"
        ),
        "error_class": "bad_params",
        "correction": (
            "Use one of: "
            + ", ".join(
                f"{m['display_name']} ('{m['id']}')"
                for m in load_materials().values()
            )
            + ". Aliases work too: 'ti', '7075', 'nylon', 'steel'."
        ),
    }


def scaled_method(base_method: Any) -> str:
    base = str(base_method or "unknown")
    return "scaled_from_calculix" if "calculix" in base else f"{base}_scaled"


def scale_result(
    base: dict[str, Any],
    target: dict[str, Any],
    part: str | None = None,
) -> dict[str, Any]:
    """Scale a solve result from its reference material to ``target``.

    Additive fields only: stress/mesh/force are carried over unchanged,
    deflection/mass/SF/method are recomputed, and a not-verified note states
    the assumptions. PA12 deflection is flagged invalid.
    """
    ref = resolve_result_material(base, part)
    out: dict[str, Any] = dict(base)
    e_ref = float(ref["youngs_modulus_mpa"])
    e_new = float(target["youngs_modulus_mpa"])
    yield_new = float(target["yield_mpa"])
    same = target["id"] == ref["id"]

    out["material_id"] = target["id"]
    out["material"] = describe(target)
    out["yield_mpa"] = yield_new
    vm = base.get("max_von_mises_mpa")
    try:
        out["safety_factor_vs_yield"] = round(yield_new / float(vm), 3) if vm else None
    except (TypeError, ValueError):
        out["safety_factor_vs_yield"] = None

    if not same:
        out["method"] = scaled_method(base.get("method"))
        out["scaled_from_material"] = ref["id"]
        for key in ("pad_deflection_mm", "tip_deflection_mm"):
            val = base.get(key)
            if val is not None:
                out[key] = round(float(val) * (e_ref / e_new), 6)
        mass = base.get("mass_kg")
        if mass is not None:
            out["mass_kg"] = round(
                float(mass) * float(target["density_kg_m3"]) / float(ref["density_kg_m3"]),
                6,
            )

    flags = [
        "stress assumed E-independent (linear elasticity; approximate for the "
        "lattice), deflection scaled by E ratio, mass by density ratio",
        "not verified: fatigue, temperature dependence, as-built AM lattice "
        "allowables, reaction forces",
    ]
    if target.get("family") == "polymer" or target["id"] == "pa12":
        out["deflection_not_verified"] = True
        flags.append(
            "PA12 deflection NOT VERIFIED: at E~1.8 GPa the linearly scaled "
            "deflection leaves the small-strain assumption — run a live solve "
            "for a usable polymer deflection"
        )
    else:
        out["deflection_not_verified"] = False
    out["scaling_notes"] = flags
    return out


def citations_for(records: list[dict[str, Any]]) -> list[str]:
    """Merged, de-duplicated source strings for a set of materials."""
    seen: list[str] = []
    for record in records:
        for src in (record.get("sources") or {}).values():
            if src not in seen:
                seen.append(src)
    return seen


def doc_sync_errors() -> list[str]:
    """Drift check: docs/materials.md must contain every material's id, E,
    density, and yield. Returns a list of mismatch descriptions (empty = ok)."""
    docs = get_settings().docs_dir / "materials.md"
    if not docs.exists():
        return ["docs/materials.md is missing"]
    text = docs.read_text(encoding="utf-8").lower()
    errors: list[str] = []
    for record in load_materials().values():
        rid = record["id"]
        needles = {
            "id": rid,
            "youngs_modulus_gpa": f"{float(record['youngs_modulus_mpa']) / 1000.0:g} gpa",
            "density": f"{float(record['density_kg_m3']):g} kg/m",
            "yield": f"{float(record['yield_mpa']):g} mpa",
        }
        for what, needle in needles.items():
            if needle not in text:
                errors.append(f"{rid}: {what} ({needle!r}) not found in docs/materials.md")
    return errors
