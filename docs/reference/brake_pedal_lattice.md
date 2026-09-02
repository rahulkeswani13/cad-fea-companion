# Brake-pedal lattice FEA notes

Simplified **aluminum 6061-T6 brake-pedal** bracket (alongside the cantilever).

## Design vs non-design

| Region | Role | Treatment |
|--------|------|-----------|
| Top pivot ring (OR20 / IR10) | Pivot attach (non-design) | Always solid |
| Pushrod clevis ring (OR15 / IR6) | Pushrod attach (non-design) | Always solid |
| Footpad (50×30×15 mm) | Load introduction (non-design) | Always solid |
| 4 mm outer rim (from `W_outer` 2D offset) | Perimeter frame (non-design) | Always solid |
| Arm pocket (inside `W_inner`, above footpad) | Design space | `solid` \| `xtruss` \| `fcc` |

## Default geometry

- Sketch in XY, extrude +Z to **15 mm** uniform thickness
- Pivot center `(0, 200)`, clevis `(40, 120)`, footpad center `(20, 0)`
- **2D-offset-first pipeline:**
  1. `W_outer` — closed XY wire: outer tangent envelope of pivot OD (20), clevis OD (15), and footpad outer corners, with **10 mm** transition fillets
  2. `W_inner = W_outer.makeOffset2D(-4)` — inside face of the continuous **4 mm** rim
  3. `Face_rim = Face(W_outer) − Face(W_inner)` → extrude +Z 15 mm → solid outer perimeter frame
  4. Solid mounting rings: pivot ID10/OD20, clevis ID6/OD15; solid footpad **50×30×15** (no lattice in footpad)
  5. **X-truss** (default) only in the **arm pocket** (inside `W_inner`, outside ring ODs, above footpad), cell **15×15 mm**, strut **2.5 mm**, ~0.5 mm overlap into rim / ring ODs
  6. Single boolean fuse of rim + rings + footpad + lattice; cut hole IDs; `isValid()` check
- FCC kept as third compare variant (3D strut cells; FEA often precomputed)
- Material: Al 6061-T6 approx `E = 69 GPa`, `nu = 0.33`, density 2700 kg/m³, yield ~276 MPa
- Load case: fix pivot ID + clevis ID; apply **+500 N** on footpad opposite (−X) face (`Fx=+500`, `Fy=Fz=0`)

## KPIs

- Mass (kg) from volume × density
- Relative density ρ\* of the pocket fill (1.0 for solid web)
- Max von Mises (MPa) and safety factor vs ~276 MPa yield
- Pad deflection (mm)

Demo recommendation rule: lowest mass among variants with **SF ≥ 1.5**.

## Tools

1. `create_brake_pedal` — solid skins + web_type lattice/solid, STEP/STL, FreeCAD GUI
2. `get_lattice_metrics` — ρ\*, volumes, mass (works for pedal or mount)
3. `apply_load_and_solve` — Gmsh + CalculiX (solid/xtruss live; FCC uses precomputed KPIs)
4. `compare_brake_pedal_variants` — solid vs X-truss vs FCC table + recommendation
5. `get_max_von_mises` — latest stress / SF

`web_type=bcc` on the pedal is accepted as an alias for `xtruss`.

## Precomputed results

Precomputed JSON under `data/results/`:

- `brake_pedal_solid_precomputed.json`
- `brake_pedal_xtruss_precomputed.json`
- `brake_pedal_fcc_precomputed.json`

Load via `POST /api/results/load_precomputed?case=brake_xtruss` (or `brake_solid` / `brake_fcc` / `brake_bcc` alias / `auto`).
