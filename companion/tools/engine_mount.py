"""Simplified aluminum engine-mount bracket: solid skins + lattice web."""

from __future__ import annotations

import json
from typing import Any

# --- Demo geometry (mm) ---
FLANGE_X = 100.0
FLANGE_Y = 60.0
FLANGE_Z = 10.0
UPRIGHT_X = 12.0
UPRIGHT_Y = 60.0
UPRIGHT_Z = 40.0  # placed on top of flange → overall height 50 mm

WEB_X0 = 12.0
WEB_LX = 40.0
WEB_Y0 = 15.0
WEB_LY = 30.0
WEB_Z0 = 10.0
WEB_LZ = 12.0

BOLT_R = 4.0
BOLT_XY = ((25.0, 30.0), (75.0, 30.0))

DEFAULT_CELL_SIZE_MM = 15.0
# r≈2.2 mm is required for Gmsh to produce volume elements on the BCC web;
# r=1.5 mm yields an empty mesh and CalculiX never writes stress results.
DEFAULT_STRUT_RADIUS_MM = 2.2
DEFAULT_NX, DEFAULT_NY, DEFAULT_NZ = 2, 2, 1
DEFAULT_FORCE_N = 20000.0  # 20 kN demo mount load — visible stress on coarse mesh
DEFAULT_MESH_MM = 3.0

AL_DENSITY_KG_M3 = 2700.0
AL_E_MPA = 69000.0
AL_NU = 0.33
AL_YIELD_MPA = 276.0

WEB_TYPES = frozenset({"solid", "bcc", "fcc"})


def pocket_volume_mm3() -> float:
    return WEB_LX * WEB_LY * WEB_LZ


def solid_skins_volume_mm3() -> float:
    """Flange + upright (no overlap double-count) minus bolt holes; no web."""
    flange = FLANGE_X * FLANGE_Y * FLANGE_Z
    upright = UPRIGHT_X * UPRIGHT_Y * UPRIGHT_Z
    holes = 2.0 * 3.141592653589793 * (BOLT_R**2) * FLANGE_Z
    return flange + upright - holes


def estimate_lattice_fill_volume_mm3(
    web_type: str,
    cell_size_mm: float,
    strut_radius_mm: float,
) -> float:
    """Rough strut fill volume inside the web pocket (demo estimate)."""
    pocket = pocket_volume_mm3()
    if web_type == "solid":
        return pocket
    # Cylinder-network estimate: scale with (r/a)^2 and architecture factor.
    a = max(cell_size_mm, 1e-6)
    r = strut_radius_mm
    ratio = (r / a) ** 2
    factor = 18.0 if web_type == "bcc" else 22.0  # FCC denser at same r/a
    rho = min(0.95, max(0.05, factor * ratio))
    return pocket * rho


def estimate_part_volume_mm3(
    web_type: str,
    cell_size_mm: float = DEFAULT_CELL_SIZE_MM,
    strut_radius_mm: float = DEFAULT_STRUT_RADIUS_MM,
) -> dict[str, float]:
    skins = solid_skins_volume_mm3()
    fill = estimate_lattice_fill_volume_mm3(web_type, cell_size_mm, strut_radius_mm)
    pocket = pocket_volume_mm3()
    total = skins + fill
    rho_star = 1.0 if web_type == "solid" else (fill / pocket if pocket else 0.0)
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
    vols = estimate_part_volume_mm3(web_type, cell_size_mm, strut_radius_mm)
    return {
        "ok": True,
        "part": "engine_mount",
        "name": "EngineMountBracket",
        "web_type": web_type,
        "cell_size_mm": cell_size_mm,
        "strut_radius_mm": strut_radius_mm,
        "nx": DEFAULT_NX,
        "ny": DEFAULT_NY,
        "nz": DEFAULT_NZ,
        "material": "Al 6061-T6 approx E=69 GPa, nu=0.33",
        "yield_mpa": AL_YIELD_MPA,
        "fixed_refs": "flange bottom face (z=0)",
        "load_refs": "upright top face (pad)",
        "step_path": None,
        "stl_path": None,
        "fcstd_path": None,
        "warning": warning,
        **vols,
    }


def precomputed_filename(web_type: str) -> str:
    return f"engine_mount_{web_type}_precomputed.json"


def fallback_fea_result(
    web_type: str,
    force_n: float,
    geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Interview-safe FEA numbers when CalculiX is unavailable."""
    vols = estimate_part_volume_mm3(
        web_type,
        float((geometry or {}).get("cell_size_mm", DEFAULT_CELL_SIZE_MM)),
        float((geometry or {}).get("strut_radius_mm", DEFAULT_STRUT_RADIUS_MM)),
    )
    # Scaled demo stresses (coarse continuum / architecture ranking).
    # Updated after fixing pad-face BCs + meshable strut radius.
    base = {
        "solid": (34.0, 0.025),
        "bcc": (36.0, 0.024),
        "fcc": (35.0, 0.024),
    }[web_type]
    scale = force_n / DEFAULT_FORCE_N
    vm = round(base[0] * scale, 4)
    delta = round(base[1] * scale, 6)
    return {
        "ok": True,
        "method": "precomputed_demo_estimate",
        "part": "engine_mount",
        "web_type": web_type,
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


def build_geometry_script(
    web_type: str,
    cell_size_mm: float,
    strut_radius_mm: float,
    out_step: str,
    out_stl: str,
    out_fcstd: str,
) -> str:
    """FreeCADCmd script: L-bracket with solid or lattice web."""
    return f"""
import json
import math
import traceback
import FreeCAD as App
import Part

def fuse_list(shapes):
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        return None
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    return out.removeSplitter()

def cyl_between(p1, p2, radius):
    import FreeCAD
    v1 = FreeCAD.Vector(*p1)
    v2 = FreeCAD.Vector(*p2)
    direction = v2.sub(v1)
    length = direction.Length
    if length < 1e-9:
        return None
    direction.normalize()
    return Part.makeCylinder(radius, length, v1, direction)

def sphere_at(p, radius):
    import FreeCAD
    return Part.makeSphere(radius, FreeCAD.Vector(*p))

def bcc_cell(ox, oy, oz, a, r):
    corners = [
        (0, 0, 0), (a, 0, 0), (0, a, 0), (a, a, 0),
        (0, 0, a), (a, 0, a), (0, a, a), (a, a, a),
    ]
    center = (a / 2.0, a / 2.0, a / 2.0)
    bits = []
    for c in corners:
        bits.append(cyl_between(center, c, r))
        bits.append(sphere_at(c, r * 1.05))
    bits.append(sphere_at(center, r * 1.05))
    cell = fuse_list(bits)
    cell.translate(App.Vector(ox, oy, oz))
    return cell

def fcc_cell(ox, oy, oz, a, r):
    # Face-centered: struts from face centers to corners on each face + edge nodes.
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
            # Connect face center to corners that lie on that face.
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

def make_lattice(web_type, x0, y0, z0, lx, ly, lz, a, r, nx, ny, nz):
    cells = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                ox = x0 + i * a
                oy = y0 + j * a
                oz = z0 + k * a
                if web_type == "bcc":
                    cells.append(bcc_cell(ox, oy, oz, a, r))
                else:
                    cells.append(fcc_cell(ox, oy, oz, a, r))
    lat = fuse_list(cells)
    pocket = Part.makeBox(lx, ly, lz)
    pocket.translate(App.Vector(x0, y0, z0))
    return lat.common(pocket)

try:
    doc = App.newDocument("EngineMount")
    web_type = "{web_type}"
    cell_size = float({cell_size_mm})
    strut_r = float({strut_radius_mm})
    nx, ny, nz = {DEFAULT_NX}, {DEFAULT_NY}, {DEFAULT_NZ}

    flange = Part.makeBox({FLANGE_X}, {FLANGE_Y}, {FLANGE_Z})
    upright = Part.makeBox({UPRIGHT_X}, {UPRIGHT_Y}, {UPRIGHT_Z})
    upright.translate(App.Vector(0, 0, {FLANGE_Z}))

    pocket_vol = {WEB_LX} * {WEB_LY} * {WEB_LZ}
    if web_type == "solid":
        web = Part.makeBox({WEB_LX}, {WEB_LY}, {WEB_LZ})
        web.translate(App.Vector({WEB_X0}, {WEB_Y0}, {WEB_Z0}))
        fill_vol = pocket_vol
        rho = 1.0
    else:
        web = make_lattice(
            web_type,
            {WEB_X0}, {WEB_Y0}, {WEB_Z0},
            {WEB_LX}, {WEB_LY}, {WEB_LZ},
            cell_size, strut_r, nx, ny, nz,
        )
        fill_vol = float(web.Volume)
        rho = fill_vol / pocket_vol if pocket_vol else 0.0

    body = fuse_list([flange, upright, web])
    for bx, by in {BOLT_XY!r}:
        hole = Part.makeCylinder({BOLT_R}, {FLANGE_Z} + 2.0, App.Vector(bx, by, -1.0))
        body = body.cut(hole)
    body = body.removeSplitter()

    obj = doc.addObject("Part::Feature", "EngineMountBracket")
    obj.Shape = body
    doc.recompute()

    skins_est = ({FLANGE_X}*{FLANGE_Y}*{FLANGE_Z}) + ({UPRIGHT_X}*{UPRIGHT_Y}*{UPRIGHT_Z})
    skins_est -= 2.0 * math.pi * ({BOLT_R}**2) * {FLANGE_Z}
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
        "part": "engine_mount",
        "name": "EngineMountBracket",
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
        "fixed_refs": "flange bottom face (z=0)",
        "load_refs": "upright top face (pad)",
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
    """FreeCADCmd FEM: rebuild mount, fix flange bottom, load upright top."""
    return f"""
import json
import math
import traceback
import FreeCAD as App
import Part
import ObjectsFem
from femmesh import gmshtools
from femtools import ccxtools

def fuse_list(shapes):
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        return None
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    return out.removeSplitter()

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

def bcc_cell(ox, oy, oz, a, r):
    corners = [
        (0, 0, 0), (a, 0, 0), (0, a, 0), (a, a, 0),
        (0, 0, a), (a, 0, a), (0, a, a), (a, a, a),
    ]
    center = (a / 2.0, a / 2.0, a / 2.0)
    bits = []
    for c in corners:
        bits.append(cyl_between(center, c, r))
        bits.append(sphere_at(c, r * 1.05))
    bits.append(sphere_at(center, r * 1.05))
    cell = fuse_list(bits)
    cell.translate(App.Vector(ox, oy, oz))
    return cell

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

def make_lattice(web_type, x0, y0, z0, lx, ly, lz, a, r, nx, ny, nz):
    cells = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                ox = x0 + i * a
                oy = y0 + j * a
                oz = z0 + k * a
                if web_type == "bcc":
                    cells.append(bcc_cell(ox, oy, oz, a, r))
                else:
                    cells.append(fcc_cell(ox, oy, oz, a, r))
    lat = fuse_list(cells)
    pocket = Part.makeBox(lx, ly, lz)
    pocket.translate(App.Vector(x0, y0, z0))
    return lat.common(pocket)

def pick_face(shape, prefer):
    # Flange underside (fixed) or upright pad top (load), not flange top.
    best = None
    best_score = -1e99
    upright_top_z = float({FLANGE_Z}) + float({UPRIGHT_Z})  # 50 mm
    for idx, face in enumerate(shape.Faces, start=1):
        try:
            n = face.normalAt(0.5, 0.5)
            c = face.CenterOfMass
            area = face.Area
        except Exception:
            continue
        score = None
        if prefer == "bottom":
            # Flange underside only (z near 0, normal -Z).
            if c.z > 1.5 or n.z > -0.5:
                continue
            score = area * 10.0 - c.z
        elif prefer == "top":
            # Upright load pad (z near overall height, normal +Z).
            # Do NOT pick flange/web tops around z=10-22.
            if c.z < (upright_top_z - 5.0) or n.z < 0.5:
                continue
            score = c.z * 100.0 + area
        if score is not None and score > best_score:
            best_score = score
            best = "Face%d" % idx
    return best

def pick_edge(shape):
    # Prefer a near-vertical edge for force direction (-Z when Reversed).
    best = None
    best_score = -1e99
    for idx, edge in enumerate(shape.Edges, start=1):
        try:
            v0 = edge.Vertexes[0].Point
            v1 = edge.Vertexes[1].Point
            dz = abs(v1.z - v0.z)
            score = dz - abs(v1.x - v0.x) - abs(v1.y - v0.y)
        except Exception:
            continue
        if score > best_score:
            best_score = score
            best = "Edge%d" % idx
    return best or "Edge1"

try:
    doc = App.newDocument("EngineMountFEM")
    web_type = "{web_type}"
    cell_size = float({cell_size_mm})
    strut_r = float({strut_radius_mm})
    force = float({force_n})
    mesh_size = float({mesh_max_size_mm})
    nx, ny, nz = {DEFAULT_NX}, {DEFAULT_NY}, {DEFAULT_NZ}

    flange = Part.makeBox({FLANGE_X}, {FLANGE_Y}, {FLANGE_Z})
    upright = Part.makeBox({UPRIGHT_X}, {UPRIGHT_Y}, {UPRIGHT_Z})
    upright.translate(App.Vector(0, 0, {FLANGE_Z}))
    pocket_vol = {WEB_LX} * {WEB_LY} * {WEB_LZ}
    if web_type == "solid":
        web = Part.makeBox({WEB_LX}, {WEB_LY}, {WEB_LZ})
        web.translate(App.Vector({WEB_X0}, {WEB_Y0}, {WEB_Z0}))
        fill_vol = pocket_vol
        rho = 1.0
    else:
        web = make_lattice(
            web_type, {WEB_X0}, {WEB_Y0}, {WEB_Z0},
            {WEB_LX}, {WEB_LY}, {WEB_LZ},
            cell_size, strut_r, nx, ny, nz,
        )
        fill_vol = float(web.Volume)
        rho = fill_vol / pocket_vol if pocket_vol else 0.0

    body = fuse_list([flange, upright, web])
    for bx, by in {BOLT_XY!r}:
        hole = Part.makeCylinder({BOLT_R}, {FLANGE_Z} + 2.0, App.Vector(bx, by, -1.0))
        body = body.cut(hole)
    body = body.removeSplitter()

    geom = doc.addObject("Part::Feature", "Mount")
    geom.Shape = body
    doc.recompute()

    fixed_face = pick_face(body, "bottom")
    load_face = pick_face(body, "top")
    dir_edge = pick_edge(body)
    if not fixed_face or not load_face:
        raise RuntimeError(
            "Could not locate flange bottom / upright pad faces "
            "(fixed=%s load=%s)." % (fixed_face, load_face)
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
    fixed.References = [(geom, fixed_face)]
    analysis.addObject(fixed)

    force_obj = ObjectsFem.makeConstraintForce(doc, "ConstraintForce")
    force_obj.References = [(geom, load_face)]
    force_obj.Force = "%s N" % force
    force_obj.Direction = (geom, [dir_edge])
    force_obj.Reversed = True
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
            "Use strut_radius_mm>=2.2 and mesh_max_size_mm~3 for BCC."
            % (n_nodes, n_vols)
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
    # Prefer showing the colored result pipeline when CalculiX created one.
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
        "part": "engine_mount",
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
        "fixed_face": fixed_face,
        "load_face": load_face,
        "fcstd_path": fcstd_path,
        "note": (
            "Live FreeCAD FEM on engine-mount bracket. Coarse tets under-predict "
            "peak strut stress; use as ranking / demo KPIs."
        ),
    }}
except Exception:
    payload = {{"ok": False, "error": traceback.format_exc()}}
print("COMPANION_JSON:" + json.dumps(payload))
"""
