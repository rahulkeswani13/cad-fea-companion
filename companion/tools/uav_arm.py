"""UAV arm (flagship F26): root clamp boss + tapered arm + tip motor ring.

``build_geometry_script`` creates the part in FreeCADCmd (STEP/STL/FCStd);
``build_fem_script`` rebuilds it and runs a static CalculiX solve (tip load on
the motor ring, clamp boss fixed). ``solid`` and ``xtruss`` variants build;
``fcc`` may land later (additive). Tool registration lives in ``cad_fea``;
editable params in ``design_program``.

Design vs non-design: the boss and motor ring stay solid, and the arm carries
flat chord rails (``CHORD_T_MM``) along its top and bottom faces — smooth,
load-bearing minimum thickness following the taper. Between the rails the
X-truss web is exposed on the sides, visible without a section view. The 2.5D
truss lives in the X-Z (bending) plane, extruded through Y. Rails and strut
ends bite into the boss and the ring's overlap zone for a clean fuse.
"""

from __future__ import annotations

import math
from typing import Any

from companion.tools import materials as mats
from companion.tools.validate import FREECAD_VALIDATION_SNIPPET, gate_call_snippet

# --- Demo geometry (mm): arm along +X, motor thrust / load along Z ---
BOSS_LX, BOSS_LY, BOSS_LZ = 36.0, 28.0, 20.0
CLAMP_BOLT_D = 3.2
CLAMP_BOLT_XS = (8.0, 28.0)
CLAMP_BOLT_Y = 9.0

ARM_LENGTH_MM = 180.0
ARM_ROOT_W, ARM_ROOT_H = 24.0, 12.0
ARM_TIP_W, ARM_TIP_H = 16.0, 8.0

RING_OR, RING_IR, RING_T = 17.0, 13.0, 8.0
RING_BITE_MM = 5.0  # ring OD bites into the arm tip so the fuse is seamless
MOTOR_BOLT_D = 3.2
MOTOR_BOLT_R = 15.0

ROOT_ENG_MM = 2.0  # rails/struts bite into the boss for a clean fuse
CHORD_T_MM = 1.5  # minimum solid thickness on the top and bottom faces
WEB_BITE_MM = 0.5  # strut ends bite into the chord rails for a clean fuse
DEFAULT_CELL_SIZE_MM = 12.0
DEFAULT_STRUT_RADIUS_MM = 1.8
DEFAULT_FORCE_N = 120.0  # motor thrust at the tip ring (demo load case)
DEFAULT_MESH_MM = 3.5

DEFAULT_MATERIAL_ID = "al6061t6"

WEB_TYPES = frozenset({"solid", "xtruss"})  # fcc lands with full F26


def normalize_web_type(web_type: str | None) -> str:
    """Map aliases (x-truss, truss, bcc, …) onto canonical UAV-arm web types."""
    wt = str(web_type or "solid").lower().strip().replace("-", "_")
    if wt in ("bcc", "x_truss", "truss", "xtruss"):
        return "xtruss"
    return wt


def tip_x(arm_length_mm: float) -> float:
    return BOSS_LX + float(arm_length_mm)


def ring_center_x(arm_length_mm: float) -> float:
    return tip_x(arm_length_mm) + RING_OR - RING_BITE_MM


def expected_bbox_dims(arm_length_mm: float = ARM_LENGTH_MM) -> list[float]:
    """Plan-first declared bounding box [X, Y, Z] in mm (F03 warn-check)."""
    return [
        BOSS_LX + float(arm_length_mm) + 2.0 * RING_OR - RING_BITE_MM,
        max(BOSS_LY, 2.0 * RING_OR),
        BOSS_LZ,
    ]


def _loft_volume_mm3(
    length_mm: float, root_w: float, root_h: float, tip_w: float, tip_h: float
) -> float:
    dw, dh = root_w - tip_w, root_h - tip_h
    area_avg = root_w * root_h - (root_w * dh + root_h * dw) / 2.0 + dw * dh / 3.0
    return length_mm * area_avg


def pocket_volume_mm3(arm_length_mm: float = ARM_LENGTH_MM) -> float:
    """Web design space: the tapered envelope between the chord rails."""
    return _loft_volume_mm3(
        arm_length_mm,
        ARM_ROOT_W,
        ARM_ROOT_H - 2.0 * CHORD_T_MM,
        ARM_TIP_W,
        ARM_TIP_H - 2.0 * CHORD_T_MM,
    )


def estimate_lattice_fill_volume_mm3(
    arm_length_mm: float = ARM_LENGTH_MM,
    cell_size_mm: float = DEFAULT_CELL_SIZE_MM,
    strut_radius_mm: float = DEFAULT_STRUT_RADIUS_MM,
) -> float:
    """Rough xtruss fill inside the pocket (demo estimate, pedal formula).

    Two diagonals per cell in the X-Z plane, extruded through the average
    pocket width, with the pedal's 0.85 overlap discount.
    """
    pocket = pocket_volume_mm3(arm_length_mm)
    a = max(float(cell_size_mm), 1e-6)
    t = max(float(strut_radius_mm), 1e-6)
    nx = max(1, int(math.ceil(float(arm_length_mm) / a - 1e-9)))
    nz = max(1, int(math.ceil((ARM_ROOT_H - 2.0 * CHORD_T_MM) / a - 1e-9)))
    width_avg = (ARM_ROOT_W + ARM_TIP_W) / 2.0
    per_cell = 2.0 * (a * math.sqrt(2.0)) * t * width_avg * 0.85
    return min(pocket * 0.95, per_cell * nx * nz)


def estimate_part_volume_mm3(
    arm_length_mm: float = ARM_LENGTH_MM,
    density_kg_m3: float | None = None,
    web_type: str = "solid",
    cell_size_mm: float = DEFAULT_CELL_SIZE_MM,
    strut_radius_mm: float = DEFAULT_STRUT_RADIUS_MM,
) -> dict[str, Any]:
    """Closed-form volume estimate: boss + tapered loft + ring, minus holes.

    Feeds the F03 gate's expected volume (warn-only band 0.5–1.5). For the
    lattice the pocket volume is replaced by the estimated strut fill.
    """
    wt = normalize_web_type(web_type)
    length = float(arm_length_mm)
    bolt_r = CLAMP_BOLT_D / 2.0
    boss = BOSS_LX * BOSS_LY * BOSS_LZ - 4.0 * math.pi * bolt_r**2 * BOSS_LZ
    arm = _loft_volume_mm3(length, ARM_ROOT_W, ARM_ROOT_H, ARM_TIP_W, ARM_TIP_H)
    ring = (
        math.pi * (RING_OR**2 - RING_IR**2) * RING_T
        - 4.0 * math.pi * (MOTOR_BOLT_D / 2.0) ** 2 * RING_T
    )
    overlap = RING_BITE_MM * ARM_TIP_W * ARM_TIP_H
    if wt == "solid":
        rails = 0.0
        pocket = arm
        fill = arm
    else:
        rails = 2.0 * _loft_volume_mm3(
            length, ARM_ROOT_W, CHORD_T_MM, ARM_TIP_W, CHORD_T_MM
        )
        pocket = pocket_volume_mm3(length)
        fill = estimate_lattice_fill_volume_mm3(length, cell_size_mm, strut_radius_mm)
    # The ring/arm overlap shrinks with the carried material fraction (solid
    # keeps the full tip-section overlap).
    carried = rails + fill
    rho_total = carried / arm if arm else 1.0
    total = boss + rails + fill + ring - overlap * rho_total
    if density_kg_m3 is None:
        density_kg_m3 = float(mats.get_material(DEFAULT_MATERIAL_ID)["density_kg_m3"])
    return {
        "boss_volume_mm3": round(boss, 3),
        "arm_volume_mm3": round(arm, 3),
        "chord_rails_volume_mm3": round(rails, 3),
        "ring_volume_mm3": round(ring, 3),
        "pocket_volume_mm3": round(pocket, 3),
        "lattice_fill_volume_mm3": round(fill, 3),
        "relative_density": 1.0 if wt == "solid" else round(fill / pocket, 4) if pocket else 0.0,
        "volume_mm3": round(total, 3),
        "mass_kg": round(total * 1e-9 * density_kg_m3, 6),
    }


# FreeCAD geometry helpers embedded in the create script (format placeholders
# are filled from the module constants; keep this string brace-free otherwise).
_FREECAD_GEOM_HELPERS = r"""
def fuse_list(shapes):
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        return None
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    try:
        return out.removeSplitter()
    except Exception:
        return out

def rect_wire_yz(x, w, h):
    pts = [
        App.Vector(x, -w / 2.0, -h / 2.0),
        App.Vector(x, w / 2.0, -h / 2.0),
        App.Vector(x, w / 2.0, h / 2.0),
        App.Vector(x, -w / 2.0, h / 2.0),
    ]
    return Part.makePolygon(pts + [pts[0]])

def tapered_loft(x0, x1, root_w, root_h, tip_w, tip_h):
    return Part.makeLoft(
        [rect_wire_yz(x0, root_w, root_h), rect_wire_yz(x1, tip_w, tip_h)], True
    )

def chord_rail(x0, x1, t, z_sign):
    # Flat minimum-thickness rail flush with the taper's top/bottom face.
    wr = rect_wire_yz(x0, {ARM_ROOT_W}, t)
    wr.translate(App.Vector(0, 0, z_sign * ({ARM_ROOT_H} / 2.0 - t / 2.0)))
    wt = rect_wire_yz(x1, {ARM_TIP_W}, t)
    wt.translate(App.Vector(0, 0, z_sign * ({ARM_TIP_H} / 2.0 - t / 2.0)))
    return Part.makeLoft([wr, wt], True)

def clamp_holes():
    r = {CLAMP_BOLT_D} / 2.0
    holes = []
    for bx in {CLAMP_BOLT_XS}:
        for by in ({CLAMP_BOLT_Y}, -{CLAMP_BOLT_Y}):
            holes.append(
                Part.makeCylinder(
                    r, {BOSS_LZ} + 2.0, App.Vector(bx, by, -{BOSS_LZ} / 2.0 - 1.0)
                )
            )
    return holes

def motor_holes(cx):
    r = {MOTOR_BOLT_D} / 2.0
    holes = []
    for ang in (45.0, 135.0, 225.0, 315.0):
        a = math.radians(ang)
        holes.append(
            Part.makeCylinder(
                r,
                {RING_T} + 2.0,
                App.Vector(
                    cx + {MOTOR_BOLT_R} * math.cos(a),
                    {MOTOR_BOLT_R} * math.sin(a),
                    -{RING_T} / 2.0 - 1.0,
                ),
            )
        )
    return holes

def xz_bar(p1, p2, half_t, yw):
    # 2.5D bar along segment p1->p2 in the X-Z plane, extruded along Y (±yw/2).
    x1, z1 = p1
    x2, z2 = p2
    dx, dz = x2 - x1, z2 - z1
    length = math.hypot(dx, dz)
    if length < 1e-9:
        return None
    ux, uz = dx / length, dz / length
    nx_, nz_ = -uz, ux
    pts = [
        App.Vector(x1 + nx_ * half_t, -yw / 2.0, z1 + nz_ * half_t),
        App.Vector(x1 - nx_ * half_t, -yw / 2.0, z1 - nz_ * half_t),
        App.Vector(x2 - nx_ * half_t, -yw / 2.0, z2 - nz_ * half_t),
        App.Vector(x2 + nx_ * half_t, -yw / 2.0, z2 + nz_ * half_t),
    ]
    wire = Part.makePolygon(pts + [pts[0]])
    return Part.Face(wire).extrude(App.Vector(0, yw, 0))

def make_xz_truss(x0, z0, lx, lz, a, t, yw, clip_solid=None):
    # Diagonal X-truss in the X-Z plane extruded through Y; clip trims taper.
    bars = []
    half = max(t, 0.5) / 2.0
    nx = max(1, int(math.ceil(lx / a - 1e-9)))
    nz = max(1, int(math.ceil(lz / a - 1e-9)))
    for i in range(nx):
        for j in range(nz):
            ox = x0 + i * a
            oz = z0 + j * a
            ax = min(a, x0 + lx - ox)
            az = min(a, z0 + lz - oz)
            if ax < t * 1.2 or az < t * 1.2:
                continue
            for seg in (((ox, oz), (ox + ax, oz + az)), ((ox + ax, oz), (ox, oz + az))):
                bar = xz_bar(seg[0], seg[1], half, yw)
                if bar is not None:
                    bars.append(bar)
    if not bars:
        return None
    lat = fuse_list(bars)
    if clip_solid is not None:
        return lat.common(clip_solid)
    return lat

def build_arm_body(web_type, arm_length, cell_size, strut_r):
    wt = str(web_type)
    if wt not in ("solid", "xtruss"):
        raise RuntimeError(
            "web_type %r not implemented yet (fcc lands with full F26)" % web_type
        )
    boss = Part.makeBox({BOSS_LX}, {BOSS_LY}, {BOSS_LZ})
    boss.translate(App.Vector(0.0, -{BOSS_LY} / 2.0, -{BOSS_LZ} / 2.0))
    for hole in clamp_holes():
        boss = boss.cut(hole)

    eng = float({ROOT_ENG_MM})
    x0, x1 = {BOSS_LX}, {BOSS_LX} + arm_length
    outer = tapered_loft(
        x0, x1, {ARM_ROOT_W}, {ARM_ROOT_H}, {ARM_TIP_W}, {ARM_TIP_H}
    )

    ring_cx = x1 + {RING_OR} - {RING_BITE_MM}
    ring = Part.makeCylinder(
        {RING_OR}, {RING_T}, App.Vector(ring_cx, 0.0, -{RING_T} / 2.0)
    ).cut(
        Part.makeCylinder(
            {RING_IR}, {RING_T} + 2.0, App.Vector(ring_cx, 0.0, -{RING_T} / 2.0 - 1.0)
        )
    )
    for hole in motor_holes(ring_cx):
        ring = ring.cut(hole)

    parts = [boss, outer, ring]
    if wt == "xtruss":
        print("COMPANION_LOG: apply_lattice — xtruss web between solid chord rails (X-Z plane)")
        chord_t = float({CHORD_T_MM})
        bite = float({WEB_BITE_MM})
        # Solid chord rails: smooth minimum-thickness top/bottom faces,
        # following the taper; they engage the boss like the web does.
        top_rail = chord_rail(x0 - eng, x1, chord_t, 1.0)
        bottom_rail = chord_rail(x0 - eng, x1, chord_t, -1.0)
        # Web design space: between the rails, grown by `bite` so strut ends
        # fuse into the rails; the boss engagement box covers the root end.
        web_h_r = {ARM_ROOT_H} - 2.0 * (chord_t - bite)
        web_h_t = {ARM_TIP_H} - 2.0 * (chord_t - bite)
        web_space = tapered_loft(x0, x1, {ARM_ROOT_W}, web_h_r, {ARM_TIP_W}, web_h_t)
        root_eng = Part.makeBox(eng, {ARM_ROOT_W}, web_h_r)
        root_eng.translate(App.Vector(x0 - eng, -{ARM_ROOT_W} / 2.0, -web_h_r / 2.0))
        clip = web_space.fuse(root_eng)
        bb = clip.BoundBox
        lattice = make_xz_truss(
            bb.XMin,
            bb.ZMin,
            bb.XLength,
            bb.ZLength,
            cell_size,
            strut_r,
            {ARM_ROOT_W},
            clip_solid=clip,
        )
        if lattice is None or float(lattice.Volume) < 1.0:
            raise RuntimeError("Lattice generation produced empty geometry")
        pocket_vol = float(web_space.Volume)
        fill_vol = float(lattice.Volume)
        rho = fill_vol / pocket_vol if pocket_vol else 0.0
        parts = [boss, ring, top_rail, bottom_rail, lattice]
    else:
        pocket_vol = float(outer.Volume)
        fill_vol = pocket_vol
        rho = 1.0

    print("COMPANION_LOG: fuse boss + arm + ring (+ lattice) (single boolean union)")
    body = fuse_list(parts)
    if body is None:
        raise RuntimeError("Final arm fuse produced empty geometry")
    # Re-cut through-holes so no fuse overlap can close them (pedal pattern).
    for hole in clamp_holes() + motor_holes(ring_cx):
        body = body.cut(hole)
    try:
        body = body.removeSplitter()
    except Exception:
        pass
    if hasattr(body, "isValid") and not body.isValid():
        raise RuntimeError("Final_Arm.isValid() returned False")
    return body, pocket_vol, fill_vol, rho
"""


def build_geometry_script(
    web_type: str,
    arm_length_mm: float = ARM_LENGTH_MM,
    out_step: str = "uav_arm.step",
    out_stl: str = "uav_arm.stl",
    out_fcstd: str = "uav_arm.fcstd",
    material_id: str = DEFAULT_MATERIAL_ID,
    cell_size_mm: float = DEFAULT_CELL_SIZE_MM,
    strut_radius_mm: float = DEFAULT_STRUT_RADIUS_MM,
    section_y_mm: float | None = None,
) -> str:
    """FreeCADCmd script: solid or xtruss UAV arm with STEP/STL/FCStd export.

    ``section_y_mm`` cuts away everything above that y-plane in the saved
    FCStd only — a mid-plane section exposing the internal lattice. STEP/STL
    always carry the full validated body (primary artifacts).
    """
    wt = normalize_web_type(web_type)
    if wt not in WEB_TYPES:
        raise ValueError(f"web_type must be one of {sorted(WEB_TYPES)}, got {web_type!r}")
    record = mats.get_material(material_id)
    if record is None:
        raise ValueError(f"unknown material {material_id!r}")
    helpers = _FREECAD_GEOM_HELPERS.format(
        BOSS_LX=BOSS_LX,
        BOSS_LY=BOSS_LY,
        BOSS_LZ=BOSS_LZ,
        CLAMP_BOLT_D=CLAMP_BOLT_D,
        CLAMP_BOLT_XS=CLAMP_BOLT_XS,
        CLAMP_BOLT_Y=CLAMP_BOLT_Y,
        ARM_ROOT_W=ARM_ROOT_W,
        ARM_ROOT_H=ARM_ROOT_H,
        ARM_TIP_W=ARM_TIP_W,
        ARM_TIP_H=ARM_TIP_H,
        RING_OR=RING_OR,
        RING_IR=RING_IR,
        RING_T=RING_T,
        RING_BITE_MM=RING_BITE_MM,
        MOTOR_BOLT_D=MOTOR_BOLT_D,
        MOTOR_BOLT_R=MOTOR_BOLT_R,
        ROOT_ENG_MM=ROOT_ENG_MM,
        CHORD_T_MM=CHORD_T_MM,
        WEB_BITE_MM=WEB_BITE_MM,
    )
    mat_desc = mats.describe(record)
    mat_density = float(record["density_kg_m3"])
    mat_yield = float(record["yield_mpa"])
    est = estimate_part_volume_mm3(
        arm_length_mm, mat_density, wt, cell_size_mm, strut_radius_mm
    )
    section_expr = "None" if section_y_mm is None else repr(float(section_y_mm))
    return f"""
import json
import math
import traceback
import FreeCAD as App
import Part

{helpers}
{FREECAD_VALIDATION_SNIPPET}

try:
    doc = App.newDocument("UavArm")
    web_type = "{wt}"
    arm_length = float({arm_length_mm})
    cell_size = float({cell_size_mm})
    strut_r = float({strut_radius_mm})
    section_y = {section_expr}

    body, pocket_vol, fill_vol, rho = build_arm_body(
        web_type, arm_length, cell_size, strut_r
    )

    obj = doc.addObject("Part::Feature", "UAVArm")
    obj.Shape = body
    doc.recompute()
{gate_call_snippet("uav_arm", est["volume_mm3"], expected_bbox_dims(arm_length_mm))}

    # STEP/STL always carry the full validated body (primary artifacts); the
    # optional y-section below only alters what the saved FCStd displays.
    total_vol = float(body.Volume)
    mass_kg = (total_vol * 1e-9) * {mat_density}

    step_path = r"{out_step}"
    stl_path = r"{out_stl}"
    fcstd_path = r"{out_fcstd}"
    Part.export([obj], step_path)
    body.exportStl(stl_path)
    if section_y is not None:
        big = 10000.0
        front = Part.makeBox(big, big, big, App.Vector(-big / 2.0, section_y, -big / 2.0))
        obj.Shape = body.cut(front)
        obj.Label = "UAVArm_section_y" + ("%g" % section_y)
        doc.recompute()
    for o in doc.Objects:
        try:
            o.Visibility = True
        except Exception:
            pass
    doc.saveAs(fcstd_path)

    payload = {{
        "ok": True,
        "part": "uav_arm",
        "name": "UAVArm",
        "web_type": web_type,
        "arm_length_mm": arm_length,
        "cell_size_mm": cell_size,
        "strut_radius_mm": strut_r,
        "section_y_mm": section_y,
        "volume_mm3": total_vol,
        "estimated_volume_mm3": {est["volume_mm3"]},
        "pocket_volume_mm3": pocket_vol,
        "lattice_fill_volume_mm3": fill_vol,
        "relative_density": rho,
        "mass_kg": mass_kg,
        "material": "{mat_desc}",
        "material_id": "{record['id']}",
        "yield_mpa": {mat_yield},
        "fixed_refs": "clamp-boss bolt-hole cylinders + boss -X face",
        "load_refs": "motor-ring annulus face (Fz, 120 N default in F26)",
        "step_path": step_path,
        "stl_path": stl_path,
        "fcstd_path": fcstd_path,
        "validation": validation,
    }}
except Exception:
    payload = {{"ok": False, "error": traceback.format_exc()}}
print("COMPANION_JSON:" + json.dumps(payload))
"""


def memory_geometry(
    web_type: str,
    arm_length_mm: float = ARM_LENGTH_MM,
    cell_size_mm: float = DEFAULT_CELL_SIZE_MM,
    strut_radius_mm: float = DEFAULT_STRUT_RADIUS_MM,
    warning: str = "",
    material_id: str = DEFAULT_MATERIAL_ID,
) -> dict[str, Any]:
    """Interview-safe geometry record when FreeCAD is absent (paths None)."""
    wt = normalize_web_type(web_type)
    record = mats.get_material(material_id) or mats.material_for_part("uav_arm")
    vols = estimate_part_volume_mm3(
        arm_length_mm, float(record["density_kg_m3"]), wt, cell_size_mm, strut_radius_mm
    )
    return {
        "ok": True,
        "part": "uav_arm",
        "name": "UAVArm",
        "web_type": wt,
        "arm_length_mm": float(arm_length_mm),
        "cell_size_mm": float(cell_size_mm),
        "strut_radius_mm": float(strut_radius_mm),
        "material": mats.describe(record),
        "material_id": record["id"],
        "yield_mpa": float(record["yield_mpa"]),
        "fixed_refs": "clamp-boss bolt-hole cylinders + boss -X face",
        "load_refs": "motor-ring top annulus faces (Fz=+120 N default)",
        "step_path": None,
        "stl_path": None,
        "fcstd_path": None,
        "warning": warning,
        **vols,
    }


def precomputed_filename(web_type: str) -> str:
    return f"uav_arm_{normalize_web_type(web_type)}_precomputed.json"


def fallback_fea_result(
    web_type: str,
    force_n: float,
    geometry: dict[str, Any] | None = None,
    material_id: str = DEFAULT_MATERIAL_ID,
) -> dict[str, Any]:
    """Interview-safe FEA numbers when CalculiX is unavailable.

    Base pair (max VM MPa, tip deflection mm) at the 120 N reference load for
    Al 6061-T6, calibrated on the committed golden CalculiX runs; stress
    scales with force, deflection with force and inverse modulus.
    """
    wt = normalize_web_type(web_type)
    record = mats.get_material(material_id) or mats.material_for_part("uav_arm")
    geo = geometry or {}
    length = float(geo.get("arm_length_mm", ARM_LENGTH_MM))
    vols = estimate_part_volume_mm3(
        length,
        float(record["density_kg_m3"]),
        wt,
        float(geo.get("cell_size_mm", DEFAULT_CELL_SIZE_MM)),
        float(geo.get("strut_radius_mm", DEFAULT_STRUT_RADIUS_MM)),
    )
    base = {"solid": (45.0, 1.0), "xtruss": (95.0, 2.4)}[wt]
    scale = float(force_n) / DEFAULT_FORCE_N
    vm = round(base[0] * scale, 4)
    al = mats.get_material("al6061t6") or record
    delta = round(
        base[1] * scale * (float(al["youngs_modulus_mpa"]) / float(record["youngs_modulus_mpa"])),
        6,
    )
    return {
        "ok": True,
        "method": "precomputed_demo_estimate",
        "part": "uav_arm",
        "web_type": wt,
        "arm_length_mm": length,
        "force_n": float(force_n),
        "mesh_max_size_mm": DEFAULT_MESH_MM,
        "max_von_mises_mpa": vm,
        "tip_deflection_mm": delta,
        "material": mats.describe(record),
        "material_id": record["id"],
        "yield_mpa": float(record["yield_mpa"]),
        "safety_factor_vs_yield": round(float(record["yield_mpa"]) / vm, 3) if vm else None,
        "fallback": True,
        "note": (
            "Demo FEA estimate when live CalculiX is unavailable (calibrated on "
            "the golden 120 N Al 6061-T6 runs). Coarse tets under-predict peak "
            "strut stress."
        ),
        **vols,
    }


class UAVArmGenerator:
    """Object-oriented entry points for geometry / lattice / FEM (demo API)."""

    def __init__(
        self,
        web_type: str = "solid",
        arm_length_mm: float = ARM_LENGTH_MM,
        cell_size_mm: float = DEFAULT_CELL_SIZE_MM,
        strut_radius_mm: float = DEFAULT_STRUT_RADIUS_MM,
    ) -> None:
        wt = normalize_web_type(web_type)
        if wt not in WEB_TYPES:
            raise ValueError(f"web_type must be one of {sorted(WEB_TYPES)}, got {web_type!r}")
        self.web_type = wt
        self.arm_length_mm = float(arm_length_mm)
        self.cell_size_mm = float(cell_size_mm)
        self.strut_radius_mm = float(strut_radius_mm)
        self._body_meta: dict[str, Any] | None = None

    def build_geometry(self) -> dict[str, Any]:
        """Record geometry params (FreeCAD build happens in build_geometry_script)."""
        vols = estimate_part_volume_mm3(
            self.arm_length_mm, web_type=self.web_type,
            cell_size_mm=self.cell_size_mm, strut_radius_mm=self.strut_radius_mm,
        )
        self._body_meta = {
            "ok": True,
            "part": "uav_arm",
            "name": "UAVArm",
            "web_type": self.web_type,
            "arm_length_mm": self.arm_length_mm,
            "cell_size_mm": self.cell_size_mm,
            "strut_radius_mm": self.strut_radius_mm,
            **vols,
        }
        return dict(self._body_meta)

    def apply_lattice(self, web_type: str | None = None) -> dict[str, Any]:
        if web_type is not None:
            wt = normalize_web_type(web_type)
            if wt not in WEB_TYPES:
                raise ValueError(f"web_type must be one of {sorted(WEB_TYPES)}, got {web_type!r}")
            self.web_type = wt
        return self.build_geometry()

    def setup_fem(
        self,
        force_n: float = DEFAULT_FORCE_N,
        mesh_max_size_mm: float = DEFAULT_MESH_MM,
    ) -> dict[str, Any]:
        """Return FEM setup metadata; live solve uses build_fem_script via companion."""
        return {
            "ok": True,
            "part": "uav_arm",
            "web_type": self.web_type,
            "force_n": force_n,
            "mesh_max_size_mm": mesh_max_size_mm,
            "fixed_refs": "clamp-boss bolt-hole cylinders + boss -X face",
            "load_refs": "motor-ring top annulus faces (Fz=+120 N)",
            "note": "Call companion apply_load_and_solve to mesh + CalculiX.",
        }


def build_fem_script(
    web_type: str,
    arm_length_mm: float,
    cell_size_mm: float,
    strut_radius_mm: float,
    force_n: float,
    mesh_max_size_mm: float,
    out_fcstd: str,
    material_id: str = DEFAULT_MATERIAL_ID,
) -> str:
    """FreeCADCmd FEM: rebuild arm, fix clamp boss, load the motor ring (+Z)."""
    wt = normalize_web_type(web_type)
    record = mats.get_material(material_id)
    if record is None:
        raise ValueError(f"unknown material {material_id!r}")
    helpers = _FREECAD_GEOM_HELPERS.format(
        BOSS_LX=BOSS_LX,
        BOSS_LY=BOSS_LY,
        BOSS_LZ=BOSS_LZ,
        CLAMP_BOLT_D=CLAMP_BOLT_D,
        CLAMP_BOLT_XS=CLAMP_BOLT_XS,
        CLAMP_BOLT_Y=CLAMP_BOLT_Y,
        ARM_ROOT_W=ARM_ROOT_W,
        ARM_ROOT_H=ARM_ROOT_H,
        ARM_TIP_W=ARM_TIP_W,
        ARM_TIP_H=ARM_TIP_H,
        RING_OR=RING_OR,
        RING_IR=RING_IR,
        RING_T=RING_T,
        RING_BITE_MM=RING_BITE_MM,
        MOTOR_BOLT_D=MOTOR_BOLT_D,
        MOTOR_BOLT_R=MOTOR_BOLT_R,
        ROOT_ENG_MM=ROOT_ENG_MM,
        CHORD_T_MM=CHORD_T_MM,
        WEB_BITE_MM=WEB_BITE_MM,
    )
    mat_desc = mats.describe(record)
    mat_name = record["display_name"]
    mat_e = float(record["youngs_modulus_mpa"])
    mat_nu = float(record["poissons_ratio"])
    mat_density = float(record["density_kg_m3"])
    mat_yield = float(record["yield_mpa"])
    est = estimate_part_volume_mm3(arm_length_mm, mat_density, wt, cell_size_mm, strut_radius_mm)
    return f"""
import json
import math
import traceback
import FreeCAD as App
import Part
import ObjectsFem
from femmesh import gmshtools
from femtools import ccxtools

{helpers}
{FREECAD_VALIDATION_SNIPPET}

def pick_bolt_faces(shape):
    # Z-axis cylinder faces of the four clamp-bolt holes.
    r = {CLAMP_BOLT_D} / 2.0
    centers = []
    for bx in {CLAMP_BOLT_XS}:
        for by in ({CLAMP_BOLT_Y}, -{CLAMP_BOLT_Y}):
            centers.append((bx, by))
    hits = []
    for idx, face in enumerate(shape.Faces, start=1):
        try:
            surf = face.Surface
            if not hasattr(surf, "Radius"):
                continue
            if abs(float(surf.Radius) - r) > 0.4:
                continue
            c = face.CenterOfMass
            for bx, by in centers:
                if abs(c.x - bx) < 1.0 and abs(c.y - by) < 1.0:
                    hits.append("Face%d" % idx)
                    break
        except Exception:
            continue
    return hits

def pick_boss_neg_x(shape):
    # Boss mounting face against the center plate (min-X, biggest area).
    best = None
    best_area = -1.0
    for idx, face in enumerate(shape.Faces, start=1):
        try:
            n = face.normalAt(0.5, 0.5)
            c = face.CenterOfMass
        except Exception:
            continue
        if n.x > -0.5 or c.x > {BOSS_LX} * 0.5:
            continue
        if face.Area > best_area:
            best_area = face.Area
            best = "Face%d" % idx
    return best

def pick_ring_top_faces(shape, tip_x):
    # Planar faces on top of the motor ring (normal +Z, z=+RING_T/2, at tip).
    ring_cx = tip_x + {RING_OR} - {RING_BITE_MM}
    hits = []
    for idx, face in enumerate(shape.Faces, start=1):
        try:
            n = face.normalAt(0.5, 0.5)
            c = face.CenterOfMass
        except Exception:
            continue
        if n.z < 0.5:
            continue
        if abs(c.z - {RING_T} / 2.0) > 0.3:
            continue
        if abs(c.x - ring_cx) > {RING_OR} + 2.0:
            continue
        hits.append("Face%d" % idx)
    return hits

def pick_z_dir_edge(shape):
    # Edge mostly along Z; return (name, reversed) so force is +Z (thrust up).
    best = None
    best_score = -1e99
    best_rev = False
    for idx, edge in enumerate(shape.Edges, start=1):
        try:
            v0 = edge.Vertexes[0].Point
            v1 = edge.Vertexes[1].Point
            dz = v1.z - v0.z
            score = abs(dz) - abs(v1.x - v0.x) - abs(v1.y - v0.y)
        except Exception:
            continue
        if score > best_score:
            best_score = score
            best = "Edge%d" % idx
            best_rev = dz < 0.0
    return best or "Edge1", best_rev

try:
    print("COMPANION_LOG: setup_fem — rebuild arm geometry + analysis")
    doc = App.newDocument("UavArmFEM")
    web_type = "{wt}"
    arm_length = float({arm_length_mm})
    cell_size = float({cell_size_mm})
    strut_r = float({strut_radius_mm})
    force = float({force_n})
    mesh_size = float({mesh_max_size_mm})

    body, pocket_vol, fill_vol, rho = build_arm_body(
        web_type, arm_length, cell_size, strut_r
    )

    geom = doc.addObject("Part::Feature", "UavArm")
    geom.Shape = body
    doc.recompute()
{gate_call_snippet("uav_arm", est["volume_mm3"], expected_bbox_dims(arm_length_mm))}

    bolt_faces = pick_bolt_faces(body)
    boss_face = pick_boss_neg_x(body)
    load_faces = pick_ring_top_faces(body, {BOSS_LX} + arm_length)
    dir_edge, force_rev = pick_z_dir_edge(body)
    if not bolt_faces or not boss_face or not load_faces:
        raise RuntimeError(
            "Could not locate clamp-bolt cylinders, boss -X face, or ring top "
            "faces (bolts=%s boss=%s load=%s)."
            % (bolt_faces, boss_face, load_faces)
        )

    analysis = ObjectsFem.makeAnalysis(doc, "Analysis")
    solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiX")
    analysis.addObject(solver)

    material = ObjectsFem.makeMaterialSolid(doc, "MechanicalMaterial")
    mat = dict(material.Material)
    mat["Name"] = "{mat_name}"
    mat["YoungsModulus"] = "{mat_e} MPa"
    mat["PoissonRatio"] = "{mat_nu}"
    mat["Density"] = "{mat_density} kg/m^3"
    material.Material = mat
    analysis.addObject(material)

    fixed = ObjectsFem.makeConstraintFixed(doc, "ConstraintFixed")
    fixed.References = [(geom, f) for f in (bolt_faces + [boss_face])]
    analysis.addObject(fixed)

    force_obj = ObjectsFem.makeConstraintForce(doc, "ConstraintForce")
    force_obj.References = [(geom, f) for f in load_faces]
    force_obj.Force = "%s N" % force
    force_obj.Direction = (geom, [dir_edge])
    # Edge + Reversed chosen so net force is +Z (Fz=+120 N, Fx=Fy=0).
    force_obj.Reversed = force_rev
    analysis.addObject(force_obj)

    mesh_obj = ObjectsFem.makeMeshGmsh(doc, "FEMMeshGmsh")
    mesh_obj.Shape = geom
    mesh_obj.CharacteristicLengthMax = "%s mm" % mesh_size
    mesh_obj.CharacteristicLengthMin = "%s mm" % (mesh_size / 2.0)
    if hasattr(mesh_obj, "ElementOrder"):
        try:
            mesh_obj.ElementOrder = "1st"
        except Exception:
            pass
    analysis.addObject(mesh_obj)
    doc.recompute()

    gmshtools.GmshTools(mesh_obj).create_mesh()
    doc.recompute()
    n_nodes = int(mesh_obj.FemMesh.NodeCount)
    n_vols = int(getattr(mesh_obj.FemMesh, "VolumeCount", 0) or 0)
    if n_nodes < 20 or n_vols < 1:
        raise RuntimeError(
            "Gmsh produced no usable volume mesh (nodes=%s volumes=%s). "
            "Use strut radius >= 1.5 mm and mesh_max_size_mm ~3.5."
            % (n_nodes, n_vols)
        )
    if n_nodes > 25000:
        raise RuntimeError(
            "Mesh too large for demo RAM budget (nodes=%s > 25000)." % n_nodes
        )

    fea = ccxtools.FemToolsCcx(analysis)
    fea.update_objects()
    fea.setup_working_dir()
    fea.setup_ccx()
    fea.purge_results()
    fea.run()

    max_vm = None
    max_disp = None
    result_obj = None
    for obj in doc.Objects:
        vm = getattr(obj, "vonMises", None)
        if vm:
            max_vm = float(max(vm))
            result_obj = obj
        disp = getattr(obj, "DisplacementLengths", None)
        if disp:
            max_disp = float(max(disp))

    fcstd_path = r"{out_fcstd}"
    for o in doc.Objects:
        try:
            o.Visibility = True
        except Exception:
            pass
    for name in ("Pipeline_CCX_Results", "CCX_Results", "Result"):
        obj = doc.getObject(name)
        if obj is not None:
            try:
                obj.Visibility = True
                if hasattr(obj, "ViewObject") and obj.ViewObject:
                    obj.ViewObject.Visibility = True
            except Exception:
                pass
    doc.saveAs(fcstd_path)

    if max_vm is None:
        raise RuntimeError("CalculiX finished but no von Mises results were found.")

    # F06: locate the peak-von-Mises node (part frame, mm).
    vm_location = None
    if result_obj is not None:
        try:
            vm_values = list(result_obj.vonMises)
            node_ids = list(getattr(result_obj, "NodeNumbers", []) or [])
            idx = max(range(len(vm_values)), key=lambda i: vm_values[i])
            nodes = mesh_obj.FemMesh.Nodes
            node = None
            if len(node_ids) == len(vm_values):
                node = nodes.get(node_ids[idx])
            if node is None:
                ordered = sorted(nodes)
                if idx < len(ordered):
                    node = nodes.get(ordered[idx])
            if node is not None:
                vm_location = [round(node.x, 3), round(node.y, 3), round(node.z, 3)]
        except Exception:
            vm_location = None

    total_vol = float(body.Volume)
    mass_kg = (total_vol * 1e-9) * {mat_density}
    payload = {{
        "ok": True,
        "method": "calculix_ccx",
        "part": "uav_arm",
        "web_type": web_type,
        "arm_length_mm": arm_length,
        "cell_size_mm": cell_size,
        "strut_radius_mm": strut_r,
        "mesh_max_size_mm": mesh_size,
        "force_n": force,
        "node_count": n_nodes,
        "max_von_mises_mpa": round(max_vm, 4),
        "max_vm_location_mm": vm_location,
        "tip_deflection_mm": round(max_disp, 6) if max_disp is not None else None,
        "volume_mm3": total_vol,
        "chord_rails_volume_mm3": {est["chord_rails_volume_mm3"]},
        "lattice_fill_volume_mm3": fill_vol,
        "pocket_volume_mm3": pocket_vol,
        "relative_density": rho,
        "mass_kg": mass_kg,
        "material": "{mat_desc}",
        "material_id": "{record['id']}",
        "yield_mpa": {mat_yield},
        "fixed_faces": bolt_faces + [boss_face],
        "load_faces": load_faces,
        "fcstd_path": fcstd_path,
        "note": (
            "Live FreeCAD FEM on the UAV arm. Coarse tets under-predict peak "
            "strut stress; use as ranking / demo KPIs. max_vm_location_mm is "
            "the peak-stress node in the part frame (x, y, z mm)."
        ),
        "validation": validation,
    }}
except Exception:
    payload = {{"ok": False, "error": traceback.format_exc()}}
print("COMPANION_JSON:" + json.dumps(payload))
"""
