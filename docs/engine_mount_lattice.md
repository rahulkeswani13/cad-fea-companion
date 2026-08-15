# Engine-mount lattice FEA notes

Simplified **aluminum 6061-T6 engine accessory / mount bracket**.

## Design vs non-design

| Region | Role | Treatment |
|--------|------|-----------|
| Base flange + 2 bolt holes | Attachment (non-design) | Always solid |
| Upright load pad | Load introduction (non-design) | Always solid |
| Web pocket (~40×30×12 mm) | Design space | `solid` \| `bcc` \| `fcc` |

## Default geometry

- Overall envelope ~100 × 60 × 50 mm
- Lattice: cell size 15 mm, strut radius 2.2 mm (meshable), 2×2×1 cells
- Material: Al 6061-T6 approx `E = 69 GPa`, `nu = 0.33`, density 2700 kg/m³, yield ~276 MPa
- Load case: fix flange bottom face; apply **20000 N** on upright top (pad) face

## KPIs

- Mass (kg) from volume × density
- Relative density ρ\* of the web fill (1.0 for solid web)
- Max von Mises (MPa) and safety factor vs ~276 MPa yield
- Pad deflection (mm)

Demo recommendation rule: lowest mass among variants with **SF ≥ 1.5**.

## Tools

1. `create_engine_mount` — solid skins + web_type lattice/solid, STEP/STL, FreeCAD GUI
2. `get_lattice_metrics` — ρ\*, volumes, mass
3. `apply_load_and_solve` — Gmsh + CalculiX (solid/BCC live; FCC uses precomputed KPIs)
4. `compare_mount_variants` — solid vs BCC vs FCC table + recommendation
5. `get_max_von_mises` — latest stress / SF

## Relative density (teaching values)

For strut lattices, relative density scales roughly with `(strut_radius / cell_size)^2` and architecture (FCC typically denser than BCC at the same radius). Typical AM strut fills often sit around **0.15–0.40** ρ\* depending on printability and stiffness targets.

Coarse tet meshes **under-predict** peak strut stress — use results for ranking variants, not certification.

## Precomputed results

Precomputed JSON under `data/results/`:

- `engine_mount_solid_precomputed.json`
- `engine_mount_bcc_precomputed.json`
- `engine_mount_fcc_precomputed.json`

Load via `POST /api/results/load_precomputed?case=bcc` (or `solid` / `fcc` / `auto`).
