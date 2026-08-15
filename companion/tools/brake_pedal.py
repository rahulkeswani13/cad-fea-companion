"""Aluminum brake-pedal lattice bracket: solid skins + lattice web (solid|xtruss|fcc)."""

from __future__ import annotations

import math
from typing import Any

# --- Demo geometry (mm) ---
THICKNESS_Z = 15.0

PIVOT_XY = (0.0, 200.0)
PIVOT_OR = 20.0
PIVOT_IR = 10.0

CLEVIS_XY = (40.0, 120.0)
CLEVIS_OR = 15.0
CLEVIS_IR = 6.0

FOOTPAD_CX, FOOTPAD_CY = 20.0, 0.0
FOOTPAD_X = 50.0
FOOTPAD_Y = 30.0
FOOTPAD_Z = THICKNESS_Z

RIM_MM = 4.0
LATTICE_OVERLAP_MM = 0.5  # strut ends bite into rim / ring OD for a clean fuse
FILLET_MM = 10.0

# Rectangular lattice design space (central arm pocket AABB; refined at runtime)
WEB_X0 = 0.0
WEB_LX = 40.0
WEB_Y0 = 45.0
WEB_LY = 90.0
WEB_Z0 = 0.0
WEB_LZ = THICKNESS_Z

DEFAULT_CELL_SIZE_MM = 15.0
# For xtruss: in-plane strut thickness (mm). For fcc: strut radius (mm).
DEFAULT_STRUT_RADIUS_MM = 2.5
DEFAULT_NX, DEFAULT_NY, DEFAULT_NZ = 3, 6, 1
DEFAULT_FORCE_N = 500.0
DEFAULT_MESH_MM = 5.0

AL_DENSITY_KG_M3 = 2700.0
AL_E_MPA = 69000.0
AL_NU = 0.33
AL_YIELD_MPA = 276.0

WEB_TYPES = frozenset({"solid", "xtruss", "fcc"})


def normalize_web_type(web_type: str | None) -> str:
    """Map aliases (bcc, x-truss, …) onto canonical brake-pedal web types."""
    wt = str(web_type or "xtruss").lower().strip().replace("-", "_")
    if wt in ("bcc", "x_truss", "truss", "xtruss"):
        return "xtruss"
    return wt


def pocket_volume_mm3() -> float:
    return WEB_LX * WEB_LY * WEB_LZ


def solid_skins_volume_mm3() -> float:
    """Rough non-design volume: rings + footpad + arm frame rim (no pocket fill)."""
    pivot_ring = math.pi * (PIVOT_OR**2 - PIVOT_IR**2) * THICKNESS_Z
    clevis_ring = math.pi * (CLEVIS_OR**2 - CLEVIS_IR**2) * THICKNESS_Z
    footpad = FOOTPAD_X * FOOTPAD_Y * FOOTPAD_Z
    peri = 2.0 * (WEB_LX + WEB_LY)
    rim_vol = peri * RIM_MM * THICKNESS_Z * 0.85
    return pivot_ring + clevis_ring + footpad + rim_vol


def estimate_lattice_fill_volume_mm3(
    web_type: str,
    cell_size_mm: float,
    strut_radius_mm: float,
) -> float:
    """Rough fill volume inside the web pocket (demo estimate)."""
    pocket = pocket_volume_mm3()
    wt = normalize_web_type(web_type)
    if wt == "solid":
        return pocket
    a = max(cell_size_mm, 1e-6)
    if wt == "xtruss":
        # Two diagonals per cell ≈ 2 * a√2 * t * thickness, overlap discount.
        t = max(strut_radius_mm, 1e-6)
        nx = max(1, int(math.ceil(WEB_LX / a - 1e-9)))
        ny = max(1, int(math.ceil(WEB_LY / a - 1e-9)))
        per_cell = 2.0 * (a * math.sqrt(2.0)) * t * THICKNESS_Z * 0.85
        return min(pocket * 0.95, per_cell * nx * ny)
    # FCC strut network
    r = strut_radius_mm
    ratio = (r / a) ** 2
    rho = min(0.95, max(0.05, 22.0 * ratio))
    return pocket * rho


def estimate_part_volume_mm3(
    web_type: str,
    cell_size_mm: float = DEFAULT_CELL_SIZE_MM,
    strut_radius_mm: float = DEFAULT_STRUT_RADIUS_MM,
) -> dict[str, float]:
    wt = normalize_web_type(web_type)
    skins = solid_skins_volume_mm3()
    fill = estimate_lattice_fill_volume_mm3(wt, cell_size_mm, strut_radius_mm)
    pocket = pocket_volume_mm3()
    total = skins + fill
    rho_star = 1.0 if wt == "solid" else (fill / pocket if pocket else 0.0)
    mass_kg = (total * 1e-9) * AL_DENSITY_KG_M3
    return {
        "skins_volume_mm3": round(skins, 3),
        "lattice_fill_volume_mm3": round(fill, 3),
        "pocket_volume_mm3": round(pocket, 3),
        "volume_mm3": round(total, 3),
        "relative_density": round(rho_star, 4),
        "mass_kg": round(mass_kg, 6),
    }


def memory_geometry(
    web_type: str,
    cell_size_mm: float,
    strut_radius_mm: float,
    warning: str,
) -> dict[str, Any]:
    wt = normalize_web_type(web_type)
    vols = estimate_part_volume_mm3(wt, cell_size_mm, strut_radius_mm)
    return {
        "ok": True,
        "part": "brake_pedal",
        "name": "BrakePedalLattice",
        "web_type": wt,
        "cell_size_mm": cell_size_mm,
        "strut_radius_mm": strut_radius_mm,
        "nx": DEFAULT_NX,
        "ny": DEFAULT_NY,
        "nz": DEFAULT_NZ,
        "material": "Al 6061-T6 approx E=69 GPa, nu=0.33",
        "yield_mpa": AL_YIELD_MPA,
        "fixed_refs": "top pivot ID + pushrod clevis ID (Z-axis cylinders)",
        "load_refs": "footpad -X face (Fx=+500 N default)",
        "step_path": None,
        "stl_path": None,
        "fcstd_path": None,
        "warning": warning,
        **vols,
    }


def precomputed_filename(web_type: str) -> str:
    return f"brake_pedal_{normalize_web_type(web_type)}_precomputed.json"


def fallback_fea_result(
    web_type: str,
    force_n: float,
    geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Interview-safe FEA numbers when CalculiX is unavailable."""
    wt = normalize_web_type(web_type)
    vols = estimate_part_volume_mm3(
        wt,
        float((geometry or {}).get("cell_size_mm", DEFAULT_CELL_SIZE_MM)),
        float((geometry or {}).get("strut_radius_mm", DEFAULT_STRUT_RADIUS_MM)),
    )
    base = {
        "solid": (12.0, 0.18),
        "xtruss": (13.8, 0.21),
        "fcc": (13.5, 0.20),
    }[wt]
    scale = force_n / DEFAULT_FORCE_N
    vm = round(base[0] * scale, 4)
    delta = round(base[1] * scale, 6)
    return {
        "ok": True,
        "method": "precomputed_demo_estimate",
        "part": "brake_pedal",
        "web_type": wt,
        "force_n": force_n,
        "mesh_max_size_mm": DEFAULT_MESH_MM,
        "max_von_mises_mpa": vm,
        "pad_deflection_mm": delta,
        "tip_deflection_mm": delta,
        "material": "Al 6061-T6 approx E=69 GPa, nu=0.33",
        "yield_mpa": AL_YIELD_MPA,
        "safety_factor_vs_yield": round(AL_YIELD_MPA / vm, 3) if vm else None,
        "fallback": True,
        "note": (
            "Demo FEA estimate when live CalculiX is unavailable. "
            "Coarse tets under-predict peak strut stress."
        ),
        **vols,
    }


# Shared FreeCAD geometry helpers embedded in both create and FEM scripts.
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

def cyl_between(p1, p2, radius):
    v1 = App.Vector(*p1)
    v2 = App.Vector(*p2)
    direction = v2.sub(v1)
    length = direction.Length
    if length < 1e-9:
        return None
    direction.normalize()
    return Part.makeCylinder(radius, length, v1, direction)

def sphere_at(p, radius):
    return Part.makeSphere(radius, App.Vector(*p))

def connector_box(p1, p2, half_w, h):
    # Extruded bar along segment p1->p2 (2.5D).
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    ux, uy = dx / length, dy / length
    nx_, ny_ = -uy, ux
    pts = [
        App.Vector(x1 + nx_ * half_w, y1 + ny_ * half_w, 0),
        App.Vector(x1 - nx_ * half_w, y1 - ny_ * half_w, 0),
        App.Vector(x2 - nx_ * half_w, y2 - ny_ * half_w, 0),
        App.Vector(x2 + nx_ * half_w, y2 + ny_ * half_w, 0),
    ]
    wire = Part.makePolygon(pts + [pts[0]])
    face = Part.Face(wire)
    return face.extrude(App.Vector(0, 0, h))

def make_xtruss(x0, y0, z0, lx, ly, lz, a, t, clip_solid=None):
    # 2.5D diagonal X-truss: extruded XY bars. Optional clip_solid encloses pocket+overlap.
    bars = []
    half = max(t, 0.5) / 2.0
    nx = max(1, int(math.ceil(lx / a - 1e-9)))
    ny = max(1, int(math.ceil(ly / a - 1e-9)))
    for i in range(nx):
        for j in range(ny):
            ox = x0 + i * a
            oy = y0 + j * a
            ax = min(a, x0 + lx - ox)
            ay = min(a, y0 + ly - oy)
            if ax < t * 1.2 or ay < t * 1.2:
                continue
            b1 = connector_box((ox, oy), (ox + ax, oy + ay), half, lz)
            b2 = connector_box((ox + ax, oy), (ox, oy + ay), half, lz)
            if b1 is not None:
                if abs(z0) > 1e-9:
                    b1.translate(App.Vector(0, 0, z0))
                bars.append(b1)
            if b2 is not None:
                if abs(z0) > 1e-9:
                    b2.translate(App.Vector(0, 0, z0))
                bars.append(b2)
    if not bars:
        return None
    lat = fuse_list(bars)
    if clip_solid is not None:
        return lat.common(clip_solid)
    pocket = Part.makeBox(lx, ly, lz)
    pocket.translate(App.Vector(x0, y0, z0))
    return lat.common(pocket)

def fcc_cell(ox, oy, oz, a, r):
    face_centers = [
        (a / 2, a / 2, 0), (a / 2, a / 2, a),
        (a / 2, 0, a / 2), (a / 2, a, a / 2),
        (0, a / 2, a / 2), (a, a / 2, a / 2),
    ]
    corners = [
        (0, 0, 0), (a, 0, 0), (0, a, 0), (a, a, 0),
        (0, 0, a), (a, 0, a), (0, a, a), (a, a, a),
    ]
    bits = []
    for fc in face_centers:
        bits.append(sphere_at(fc, r * 1.05))
        for c in corners:
            tol = 1e-6
            on_face = (
                (abs(fc[2]) < tol and abs(c[2]) < tol)
                or (abs(fc[2] - a) < tol and abs(c[2] - a) < tol)
                or (abs(fc[1]) < tol and abs(c[1]) < tol)
                or (abs(fc[1] - a) < tol and abs(c[1] - a) < tol)
                or (abs(fc[0]) < tol and abs(c[0]) < tol)
                or (abs(fc[0] - a) < tol and abs(c[0] - a) < tol)
            )
            if on_face:
                bits.append(cyl_between(fc, c, r))
    for c in corners:
        bits.append(sphere_at(c, r * 1.05))
    cell = fuse_list([b for b in bits if b is not None])
    cell.translate(App.Vector(ox, oy, oz))
    return cell

def make_lattice(web_type, x0, y0, z0, lx, ly, lz, a, strut, nx, ny, nz, clip_solid=None):
    if web_type == "xtruss":
        return make_xtruss(x0, y0, z0, lx, ly, lz, a, strut, clip_solid=clip_solid)
    cells = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                ox = x0 + i * a
                oy = y0 + j * a
                oz = z0 + k * a
                cells.append(fcc_cell(ox, oy, oz, a, strut))
    lat = fuse_list(cells)
    if clip_solid is not None:
        return lat.common(clip_solid)
    pocket = Part.makeBox(lx, ly, lz)
    pocket.translate(App.Vector(x0, y0, z0))
    return lat.common(pocket)

def circle_face_xy(cx, cy, radius):
    wire = Part.Wire([Part.makeCircle(radius, App.Vector(cx, cy, 0), App.Vector(0, 0, 1))])
    return Part.Face(wire)

def rect_face_xy(x0, y0, lx, ly):
    pts = [
        App.Vector(x0, y0, 0),
        App.Vector(x0 + lx, y0, 0),
        App.Vector(x0 + lx, y0 + ly, 0),
        App.Vector(x0, y0 + ly, 0),
    ]
    return Part.Face(Part.makePolygon(pts + [pts[0]]))

def connector_face_xy(p1, p2, half_w):
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    ux, uy = dx / length, dy / length
    nx_, ny_ = -uy, ux
    pts = [
        App.Vector(x1 + nx_ * half_w, y1 + ny_ * half_w, 0),
        App.Vector(x1 - nx_ * half_w, y1 - ny_ * half_w, 0),
        App.Vector(x2 - nx_ * half_w, y2 - ny_ * half_w, 0),
        App.Vector(x2 + nx_ * half_w, y2 + ny_ * half_w, 0),
    ]
    return Part.Face(Part.makePolygon(pts + [pts[0]]))

def external_tangent_band_face(c1, r1, c2, r2):
    # Planar band between the two direct common external tangents of two circles.
    x1, y1 = float(c1[0]), float(c1[1])
    x2, y2 = float(c2[0]), float(c2[1])
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy)
    if dist <= abs(r1 - r2) + 1e-6:
        return None
    base = math.atan2(dy, dx)
    alpha = math.asin(max(-1.0, min(1.0, (r1 - r2) / dist)))
    pts = []
    for side in (1.0, -1.0):
        ang = base + side * (math.pi / 2.0 - alpha)
        nx, ny = math.cos(ang), math.sin(ang)
        pts.append(App.Vector(x1 + r1 * nx, y1 + r1 * ny, 0))
        pts.append(App.Vector(x2 + r2 * nx, y2 + r2 * ny, 0))
    # pts order: p1a, p2a, p1b, p2b → reorder to closed quad p1a,p2a,p2b,p1b
    quad = [pts[0], pts[1], pts[3], pts[2], pts[0]]
    return Part.Face(Part.makePolygon(quad))

def fillet_wire_xy(wire, radius):
    # Fillet vertical corners of a planar wire via a short extrusion, then re-extract z≈0 wire.
    if radius <= 1e-6:
        return wire
    face = Part.Face(wire)
    solid = face.extrude(App.Vector(0, 0, 1.0))
    edges = []
    for e in solid.Edges:
        try:
            v0 = e.Vertexes[0].Point
            v1 = e.Vertexes[1].Point
            if abs(v1.z - v0.z) > 0.5 and abs(v1.x - v0.x) < 1e-3 and abs(v1.y - v0.y) < 1e-3:
                edges.append(e)
        except Exception:
            continue
    if not edges:
        return wire
    filleted = None
    for n in (len(edges), 12, 8, 4):
        try:
            filleted = solid.makeFillet(float(radius), edges[:n])
            break
        except Exception:
            continue
    if filleted is None:
        return wire
    best = None
    best_score = 1e99
    for f in filleted.Faces:
        try:
            n = f.normalAt(0.5, 0.5)
            if abs(n.z) < 0.9:
                continue
            c = f.CenterOfMass
            score = abs(c.z)
            if score < best_score:
                best_score = score
                best = f
        except Exception:
            continue
    if best is None:
        return wire
    try:
        return best.OuterWire
    except Exception:
        return wire

def offset_wire_inward(wire, distance):
    # 2D inward offset (negative makeOffset2D). Returns a closed Wire.
    dist = -abs(float(distance))
    result = None
    try:
        result = wire.makeOffset2D(dist)
    except Exception:
        result = None
    if result is None:
        try:
            result = Part.Face(wire).makeOffset2D(dist)
        except Exception:
            result = None
    if result is None:
        raise RuntimeError("makeOffset2D failed for outer boundary wire")
    if result.ShapeType == "Wire":
        return result
    if result.ShapeType == "Compound":
        wires = [w for w in result.Wires if w.isClosed()]
        if not wires:
            raise RuntimeError("makeOffset2D returned no closed wires")
        wires.sort(key=lambda w: Part.Face(w).Area, reverse=True)
        return wires[0]
    if result.ShapeType == "Face":
        return result.OuterWire
    wires = getattr(result, "Wires", None) or []
    if wires:
        return wires[0]
    raise RuntimeError("Unexpected makeOffset2D result: %s" % result.ShapeType)

def silhouette_outer_wire(sil):
    # Coplanar Face.fuse often leaves a Compound of faces; never keep only the largest.
    if sil is None:
        raise RuntimeError("Empty silhouette")
    if sil.ShapeType == "Face":
        return sil.OuterWire
    faces = list(getattr(sil, "Faces", []) or [])
    if not faces:
        raise RuntimeError("Silhouette has no planar face for OuterWire")
    if len(faces) == 1:
        return faces[0].OuterWire
    # Extrude → fuse → single solid → re-extract planar outer wire at z≈0.
    solids = []
    for f in faces:
        try:
            solids.append(f.extrude(App.Vector(0, 0, 1.0)))
        except Exception:
            continue
    body = fuse_list(solids)
    if body is None:
        raise RuntimeError("Failed to fuse silhouette faces")
    try:
        body = body.removeSplitter()
    except Exception:
        pass
    best = None
    best_score = 1e99
    for f in body.Faces:
        try:
            n = f.normalAt(0.5, 0.5)
            if abs(n.z) < 0.9:
                continue
            score = abs(f.CenterOfMass.z)
            if score < best_score:
                best_score = score
                best = f
        except Exception:
            continue
    if best is None:
        # Fallback: largest face area among original faces still wrong — use bbox shell.
        raise RuntimeError("Could not extract fused silhouette OuterWire")
    return best.OuterWire

def build_w_outer(px, py, pivot_or, cx, cy, clevis_or, fx0, fy0, foot_x, foot_y, fillet_mm, rim_mm):
    # Outer envelope: tangent + arm pivot↔clevis; prior-width arm clevis→footpad; footpad outline.
    print("COMPANION_LOG: build_geometry — W_outer (2D tangent envelope)")
    arm_half = max(16.0, float(rim_mm) * 3.0 + 6.0)
    faces = [
        circle_face_xy(px, py, pivot_or),
        circle_face_xy(cx, cy, clevis_or),
        rect_face_xy(fx0, fy0, foot_x, foot_y),
    ]
    # Upper arm: external tangents (smooth OD envelope) + prior-width connector (guarantees join).
    band_pc = external_tangent_band_face((px, py), pivot_or, (cx, cy), clevis_or)
    if band_pc is not None:
        faces.append(band_pc)
    arm_pc = connector_face_xy((px, py), (cx, cy), arm_half)
    if arm_pc is not None:
        faces.append(arm_pc)
    # Lower arm: prior-width connector only (not full footpad-width bar).
    foot_cx = fx0 + 0.5 * foot_x
    foot_cy = fy0 + 0.5 * foot_y
    arm_cf = connector_face_xy((cx, cy), (foot_cx, foot_cy), arm_half)
    if arm_cf is not None:
        faces.append(arm_cf)
    sil = fuse_list(faces)
    if sil is None:
        raise RuntimeError("Failed to build 2D silhouette for W_outer")
    try:
        sil = sil.removeSplitter()
    except Exception:
        pass
    w = silhouette_outer_wire(sil)
    w = fillet_wire_xy(w, float(fillet_mm))
    if not w.isClosed():
        raise RuntimeError("W_outer is not closed")
    # Sanity: envelope must cover both hole centers.
    fo = Part.Face(w)
    for pt, label in (
        (App.Vector(px, py, 0), "pivot"),
        (App.Vector(cx, cy, 0), "clevis"),
        (App.Vector(foot_cx, foot_cy, 0), "footpad"),
    ):
        if fo.distToShape(Part.Vertex(pt))[0] > 1e-3:
            # Center may lie in a hole cut later; require it inside outer face (not outside).
            if not fo.isInside(pt, 1e-3, True):
                raise RuntimeError("W_outer does not contain %s center — upper/lower arm disconnected" % label)
    return w

def build_pedal_body(web_type, cell_size, strut_r, nx, ny, nz):
    h = float({THICKNESS_Z})
    rim = float({RIM_MM})
    overlap = float({LATTICE_OVERLAP_MM})
    fillet = float({FILLET_MM})
    px, py = {PIVOT_XY[0]}, {PIVOT_XY[1]}
    cx, cy = {CLEVIS_XY[0]}, {CLEVIS_XY[1]}
    pivot_or = float({PIVOT_OR})
    pivot_ir = float({PIVOT_IR})
    clevis_or = float({CLEVIS_OR})
    clevis_ir = float({CLEVIS_IR})
    fx0 = {FOOTPAD_CX} - {FOOTPAD_X} / 2.0
    fy0 = {FOOTPAD_CY} - {FOOTPAD_Y} / 2.0
    foot_x = float({FOOTPAD_X})
    foot_y = float({FOOTPAD_Y})

    # --- Step 1: W_outer (2D) ---
    w_outer = build_w_outer(
        px, py, pivot_or, cx, cy, clevis_or, fx0, fy0, foot_x, foot_y, fillet, rim
    )

    # --- Step 2: inward 2D offset → inner rim wire ---
    print("COMPANION_LOG: build_geometry — W_inner_rim = makeOffset2D(-%s)" % rim)
    w_inner = offset_wire_inward(w_outer, rim)

    # --- Step 3: planar rim face → extrude 15 mm outer perimeter frame ---
    print("COMPANION_LOG: build_geometry — Solid_Outer_Rim (extrude Face_rim)")
    face_outer = Part.Face(w_outer)
    face_inner = Part.Face(w_inner)
    face_rim = face_outer.cut(face_inner)
    solid_outer_rim = face_rim.extrude(App.Vector(0, 0, h))

    # --- Step 4: solid mounting rings + solid footpad ---
    print("COMPANION_LOG: build_geometry — pivot/clevis rings + solid footpad")
    top_ring = Part.makeCylinder(pivot_or, h, App.Vector(px, py, 0)).cut(
        Part.makeCylinder(pivot_ir, h + 2.0, App.Vector(px, py, -1.0))
    )
    clevis_ring = Part.makeCylinder(clevis_or, h, App.Vector(cx, cy, 0)).cut(
        Part.makeCylinder(clevis_ir, h + 2.0, App.Vector(cx, cy, -1.0))
    )
    footpad = Part.makeBox(foot_x, foot_y, h)
    footpad.translate(App.Vector(fx0, fy0, 0))

    # Arm pocket = inside W_inner, excluding solid footpad + ring OD discs (lattice stays in arm only).
    footpad_face = rect_face_xy(fx0, fy0, foot_x, foot_y)
    pivot_od_face = circle_face_xy(px, py, pivot_or)
    clevis_od_face = circle_face_xy(cx, cy, clevis_or)
    arm_pocket_face = face_inner.cut(footpad_face).cut(pivot_od_face).cut(clevis_od_face)
    try:
        arm_pocket_face = arm_pocket_face.removeSplitter()
    except Exception:
        pass
    if arm_pocket_face is None or float(getattr(arm_pocket_face, "Area", 0.0) or 0.0) < 1.0:
        raise RuntimeError("Arm pocket face is empty after cutting footpad/rings")
    pocket = arm_pocket_face.extrude(App.Vector(0, 0, h))
    pocket_vol = float(pocket.Volume)

    print("COMPANION_LOG: apply_lattice — web_type=%s (arm pocket only)" % web_type)
    if web_type == "solid":
        fill = pocket
        fill_vol = pocket_vol
        rho = 1.0
        lattice = None
    else:
        # Clip lattice to pocket grown by ~overlap so struts fuse into rim + ring ODs.
        clip_face = None
        try:
            clip_face = arm_pocket_face.makeOffset2D(float(overlap))
        except Exception:
            clip_face = None
        if clip_face is not None and clip_face.ShapeType == "Compound":
            cw = [w for w in clip_face.Wires if w.isClosed()]
            if cw:
                cw.sort(key=lambda w: abs(Part.Face(w).Area), reverse=True)
                clip_face = Part.Face(cw[0])
        if clip_face is not None and clip_face.ShapeType == "Wire":
            clip_face = Part.Face(clip_face)
        if clip_face is None or float(getattr(clip_face, "Area", 0.0) or 0.0) < 1.0:
            clip_face = arm_pocket_face
        # Keep inside outer envelope; allow bite into rim / ring OD; never enter hole IDs or footpad.
        clip_face = clip_face.common(face_outer).cut(footpad_face)
        pivot_hole_face = circle_face_xy(px, py, pivot_ir)
        clevis_hole_face = circle_face_xy(cx, cy, clevis_ir)
        clip_face = clip_face.cut(pivot_hole_face).cut(clevis_hole_face)
        clip = clip_face.extrude(App.Vector(0, 0, h))

        bb = clip.BoundBox
        lattice = make_lattice(
            web_type,
            bb.XMin, bb.YMin, bb.ZMin,
            bb.XLength, bb.YLength, bb.ZLength,
            cell_size, strut_r, nx, ny, nz,
            clip_solid=clip,
        )
        if lattice is None:
            raise RuntimeError("Lattice generation produced empty geometry")
        fill_vol = float(lattice.Volume)
        rho = fill_vol / pocket_vol if pocket_vol else 0.0
        fill = lattice

    # --- Step 6: single unified boolean fuse ---
    print("COMPANION_LOG: fuse rim + rings + footpad + fill (single boolean union)")
    parts = [solid_outer_rim, top_ring, clevis_ring, footpad]
    if fill is not None:
        parts.append(fill)
    body = fuse_list(parts)
    if body is None:
        raise RuntimeError("Final pedal fuse produced empty geometry")

    # Ensure through-holes stay open even if rim/fill overlapped IDs.
    pivot_hole = Part.makeCylinder(pivot_ir, h + 2.0, App.Vector(px, py, -1.0))
    clevis_hole = Part.makeCylinder(clevis_ir, h + 2.0, App.Vector(cx, cy, -1.0))
    body = body.cut(pivot_hole).cut(clevis_hole)
    try:
        body = body.removeSplitter()
    except Exception:
        pass
    if hasattr(body, "isValid") and not body.isValid():
        raise RuntimeError("Final_Pedal.isValid() returned False")
    return body, pocket_vol, fill_vol, rho
"""


class BrakePedalLatticeGenerator:
    """Object-oriented entry points for geometry / lattice / FEM (demo API)."""

    def __init__(
        self,
        web_type: str = "xtruss",
        cell_size_mm: float = DEFAULT_CELL_SIZE_MM,
        strut_radius_mm: float = DEFAULT_STRUT_RADIUS_MM,
    ) -> None:
        wt = normalize_web_type(web_type)
        if wt not in WEB_TYPES:
            raise ValueError(f"web_type must be one of {sorted(WEB_TYPES)}, got {web_type!r}")
        self.web_type = wt
        self.cell_size_mm = float(cell_size_mm)
        self.strut_radius_mm = float(strut_radius_mm)
        self.nx = DEFAULT_NX
        self.ny = DEFAULT_NY
        self.nz = DEFAULT_NZ
        self._body_meta: dict[str, Any] | None = None

    def build_geometry(self) -> dict[str, Any]:
        """Record geometry params (FreeCAD build happens in build_geometry_script)."""
        vols = estimate_part_volume_mm3(
            self.web_type, self.cell_size_mm, self.strut_radius_mm
        )
        self._body_meta = {
            "ok": True,
            "part": "brake_pedal",
            "name": "BrakePedalLattice",
            "web_type": self.web_type,
            "cell_size_mm": self.cell_size_mm,
            "strut_radius_mm": self.strut_radius_mm,
            "nx": self.nx,
            "ny": self.ny,
            "nz": self.nz,
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
            "part": "brake_pedal",
            "web_type": self.web_type,
            "force_n": force_n,
            "mesh_max_size_mm": mesh_max_size_mm,
            "material": "Al 6061-T6 approx E=69 GPa, nu=0.33",
            "fixed_refs": "top pivot ID + pushrod clevis ID",
            "load_refs": "footpad -X face (Fx=+500 N)",
            "note": "Call companion apply_load_and_solve to mesh + CalculiX.",
        }


def build_geometry_script(
    web_type: str,
    cell_size_mm: float,
    strut_radius_mm: float,
    out_step: str,
    out_stl: str,
    out_fcstd: str,
) -> str:
    """FreeCADCmd script: brake pedal with solid or lattice web."""
    helpers = _FREECAD_GEOM_HELPERS.format(
        THICKNESS_Z=THICKNESS_Z,
        PIVOT_XY=PIVOT_XY,
        CLEVIS_XY=CLEVIS_XY,
        FOOTPAD_CX=FOOTPAD_CX,
        FOOTPAD_CY=FOOTPAD_CY,
        FOOTPAD_X=FOOTPAD_X,
        FOOTPAD_Y=FOOTPAD_Y,
        PIVOT_OR=PIVOT_OR,
        PIVOT_IR=PIVOT_IR,
        CLEVIS_OR=CLEVIS_OR,
        CLEVIS_IR=CLEVIS_IR,
        FILLET_MM=FILLET_MM,
        RIM_MM=RIM_MM,
        LATTICE_OVERLAP_MM=LATTICE_OVERLAP_MM,
        WEB_X0=WEB_X0,
        WEB_Y0=WEB_Y0,
        WEB_Z0=WEB_Z0,
        WEB_LX=WEB_LX,
        WEB_LY=WEB_LY,
        WEB_LZ=WEB_LZ,
    )
    return f"""
import json
import math
import traceback
import FreeCAD as App
import Part

{helpers}

try:
    doc = App.newDocument("BrakePedal")
    web_type = "{web_type}"
    cell_size = float({cell_size_mm})
    strut_r = float({strut_radius_mm})
    nx, ny, nz = {DEFAULT_NX}, {DEFAULT_NY}, {DEFAULT_NZ}

    body, pocket_vol, fill_vol, rho = build_pedal_body(
        web_type, cell_size, strut_r, nx, ny, nz
    )

    obj = doc.addObject("Part::Feature", "BrakePedalLattice")
    obj.Shape = body
    doc.recompute()

    skins_est = {solid_skins_volume_mm3()}
    total_vol = float(body.Volume)
    mass_kg = (total_vol * 1e-9) * {AL_DENSITY_KG_M3}

    step_path = r"{out_step}"
    stl_path = r"{out_stl}"
    fcstd_path = r"{out_fcstd}"
    Part.export([obj], step_path)
    body.exportStl(stl_path)
    for o in doc.Objects:
        try:
            o.Visibility = True
        except Exception:
            pass
    doc.saveAs(fcstd_path)

    payload = {{
        "ok": True,
        "part": "brake_pedal",
        "name": "BrakePedalLattice",
        "web_type": web_type,
        "cell_size_mm": cell_size,
        "strut_radius_mm": strut_r,
        "nx": nx, "ny": ny, "nz": nz,
        "volume_mm3": total_vol,
        "skins_volume_mm3": skins_est,
        "lattice_fill_volume_mm3": fill_vol,
        "pocket_volume_mm3": pocket_vol,
        "relative_density": rho,
        "mass_kg": mass_kg,
        "material": "Al 6061-T6 approx E=69 GPa, nu=0.33",
        "yield_mpa": {AL_YIELD_MPA},
        "fixed_refs": "top pivot ID + pushrod clevis ID (Z-axis cylinders)",
        "load_refs": "footpad -X face (Fx=+500 N)",
        "step_path": step_path,
        "stl_path": stl_path,
        "fcstd_path": fcstd_path,
    }}
except Exception:
    payload = {{"ok": False, "error": traceback.format_exc()}}
print("COMPANION_JSON:" + json.dumps(payload))
"""


def build_fem_script(
    web_type: str,
    cell_size_mm: float,
    strut_radius_mm: float,
    force_n: float,
    mesh_max_size_mm: float,
    out_fcstd: str,
) -> str:
    """FreeCADCmd FEM: rebuild pedal, fix hole IDs, load footpad -X."""
    helpers = _FREECAD_GEOM_HELPERS.format(
        THICKNESS_Z=THICKNESS_Z,
        PIVOT_XY=PIVOT_XY,
        CLEVIS_XY=CLEVIS_XY,
        FOOTPAD_CX=FOOTPAD_CX,
        FOOTPAD_CY=FOOTPAD_CY,
        FOOTPAD_X=FOOTPAD_X,
        FOOTPAD_Y=FOOTPAD_Y,
        PIVOT_OR=PIVOT_OR,
        PIVOT_IR=PIVOT_IR,
        CLEVIS_OR=CLEVIS_OR,
        CLEVIS_IR=CLEVIS_IR,
        FILLET_MM=FILLET_MM,
        RIM_MM=RIM_MM,
        LATTICE_OVERLAP_MM=LATTICE_OVERLAP_MM,
        WEB_X0=WEB_X0,
        WEB_Y0=WEB_Y0,
        WEB_Z0=WEB_Z0,
        WEB_LX=WEB_LX,
        WEB_LY=WEB_LY,
        WEB_LZ=WEB_LZ,
    )
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

def pick_cylinder_faces(shape, cx, cy, expected_r, tol_xy=3.0, tol_r=2.5):
    hits = []
    for idx, face in enumerate(shape.Faces, start=1):
        try:
            surf = face.Surface
            # Cylindrical surfaces expose Axis / Radius in OCC wrappers.
            if not hasattr(surf, "Radius"):
                continue
            r = float(surf.Radius)
            if abs(r - expected_r) > tol_r:
                continue
            c = face.CenterOfMass
            if abs(c.x - cx) > tol_xy or abs(c.y - cy) > tol_xy:
                continue
            hits.append("Face%d" % idx)
        except Exception:
            continue
    return hits

def pick_footpad_neg_x(shape):
    # Opposite (min-X) footpad face — load direction is +X (Fx=+500).
    fx_min = {FOOTPAD_CX} - {FOOTPAD_X} / 2.0
    best = None
    best_score = -1e99
    for idx, face in enumerate(shape.Faces, start=1):
        try:
            n = face.normalAt(0.5, 0.5)
            c = face.CenterOfMass
            area = face.Area
        except Exception:
            continue
        if n.x > -0.5:
            continue
        if c.x > fx_min + 8.0:
            continue
        if abs(c.y - {FOOTPAD_CY}) > {FOOTPAD_Y}:
            continue
        score = area * 10.0 - c.x
        if score > best_score:
            best_score = score
            best = "Face%d" % idx
    return best

def pick_x_dir_edge(shape):
    # Edge mostly along X; return (name, reversed) so force is +X.
    best = None
    best_score = -1e99
    best_rev = False
    for idx, edge in enumerate(shape.Edges, start=1):
        try:
            v0 = edge.Vertexes[0].Point
            v1 = edge.Vertexes[1].Point
            dx = v1.x - v0.x
            score = abs(dx) - abs(v1.y - v0.y) - abs(v1.z - v0.z)
        except Exception:
            continue
        if score > best_score:
            best_score = score
            best = "Edge%d" % idx
            # Want net force +X: reverse when edge runs -X.
            best_rev = dx < 0.0
    return best or "Edge1", best_rev

try:
    print("COMPANION_LOG: setup_fem — rebuild geometry + analysis")
    doc = App.newDocument("BrakePedalFEM")
    web_type = "{web_type}"
    cell_size = float({cell_size_mm})
    strut_r = float({strut_radius_mm})
    force = float({force_n})
    mesh_size = float({mesh_max_size_mm})
    nx, ny, nz = {DEFAULT_NX}, {DEFAULT_NY}, {DEFAULT_NZ}

    body, pocket_vol, fill_vol, rho = build_pedal_body(
        web_type, cell_size, strut_r, nx, ny, nz
    )

    geom = doc.addObject("Part::Feature", "Pedal")
    geom.Shape = body
    doc.recompute()

    pivot_faces = pick_cylinder_faces(body, {PIVOT_XY[0]}, {PIVOT_XY[1]}, {PIVOT_IR})
    clevis_faces = pick_cylinder_faces(body, {CLEVIS_XY[0]}, {CLEVIS_XY[1]}, {CLEVIS_IR})
    load_face = pick_footpad_neg_x(body)
    dir_edge, force_rev = pick_x_dir_edge(body)
    if not pivot_faces or not clevis_faces or not load_face:
        raise RuntimeError(
            "Could not locate pivot/clevis ID or footpad -X face "
            "(pivot=%s clevis=%s load=%s)."
            % (pivot_faces, clevis_faces, load_face)
        )

    analysis = ObjectsFem.makeAnalysis(doc, "Analysis")
    solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiX")
    analysis.addObject(solver)

    material = ObjectsFem.makeMaterialSolid(doc, "MechanicalMaterial")
    mat = dict(material.Material)
    mat["Name"] = "Al6061-T6"
    mat["YoungsModulus"] = "{AL_E_MPA} MPa"
    mat["PoissonRatio"] = "{AL_NU}"
    mat["Density"] = "{AL_DENSITY_KG_M3} kg/m^3"
    material.Material = mat
    analysis.addObject(material)

    fixed = ObjectsFem.makeConstraintFixed(doc, "ConstraintFixed")
    fixed.References = [(geom, f) for f in (pivot_faces + clevis_faces)]
    analysis.addObject(fixed)

    force_obj = ObjectsFem.makeConstraintForce(doc, "ConstraintForce")
    force_obj.References = [(geom, load_face)]
    force_obj.Force = "%s N" % force
    force_obj.Direction = (geom, [dir_edge])
    # Edge + Reversed chosen so net force is +X (Fx=+500 N, Fy=0, Fz=0).
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
            "Use strut thickness ~2.5 mm (xtruss) or radius>=2.2 (fcc) and mesh_max_size_mm~5."
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
    total_vol = float(body.Volume)
    mass_kg = (total_vol * 1e-9) * {AL_DENSITY_KG_M3}
    payload = {{
        "ok": True,
        "method": "calculix_ccx",
        "part": "brake_pedal",
        "web_type": web_type,
        "mesh_max_size_mm": mesh_size,
        "force_n": force,
        "node_count": n_nodes,
        "max_von_mises_mpa": round(max_vm, 4),
        "pad_deflection_mm": round(max_disp, 6) if max_disp is not None else None,
        "tip_deflection_mm": round(max_disp, 6) if max_disp is not None else None,
        "volume_mm3": total_vol,
        "lattice_fill_volume_mm3": fill_vol,
        "pocket_volume_mm3": pocket_vol,
        "relative_density": rho,
        "mass_kg": mass_kg,
        "material": "Al 6061-T6 approx E=69 GPa, nu=0.33",
        "yield_mpa": {AL_YIELD_MPA},
        "fixed_faces": pivot_faces + clevis_faces,
        "load_face": load_face,
        "fcstd_path": fcstd_path,
        "note": (
            "Live FreeCAD FEM on brake-pedal lattice. Coarse tets under-predict "
            "peak strut stress; use as ranking / demo KPIs."
        ),
    }}
except Exception:
    payload = {{"ok": False, "error": traceback.format_exc()}}
print("COMPANION_JSON:" + json.dumps(payload))
"""
