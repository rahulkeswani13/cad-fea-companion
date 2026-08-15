# FreeCAD FEM companion notes

## Brake-pedal lattice (primary)

- **Brake pedal**: solid pivot + clevis rings + footpad; web = solid | **xtruss** | FCC.
- Default lattice is a **2.5D diagonal X-truss** (15 mm cells, 2.5 mm strut thickness) — not BCC.
- Keep meshes **coarse** (~5 mm max element size; target **&lt;25k nodes**).
- Peak RAM is often during meshing; prefer one FreeCAD solve at a time.
- FCC FEA KPIs are precomputed by design (geometry/metrics still live).

### Recommended pedal load case

- Material: Al 6061-T6 approx `E = 69 GPa`, `nu = 0.33`
- Fixed: top pivot ID + pushrod clevis ID (Z-axis cylinders)
- Load: **+500 N** on footpad opposite (−X) face (`Fx = +500`, `Fy = Fz = 0`)
- Continuous **4 mm** rim on all borders via `makeThickness` (same wall idea as hole rings)
- `web_type=bcc` aliases to `xtruss` on the pedal.

See `docs/brake_pedal_lattice.md` for KPIs and design vs non-design regions.

## Engine-mount lattice demo (secondary)

- Simplified **L-bracket** engine mount: solid flange + upright pad; web = solid | BCC | FCC.
- Keep meshes **coarse** (about 3–4 mm max element size on the solid; lattice may fall back to precomputed).
- FCC FEA KPIs are precomputed by design (geometry/metrics still live).

### Recommended mount load case

- Material: Al 6061-T6 approx `E = 69 GPa`, `nu = 0.33`
- Fixed: flange bottom face
- Load: **20000 N** on upright top (pad)
- Lattice defaults: cell 15 mm, strut radius **2.2 mm**, 2×2×1 cells

See `docs/engine_mount_lattice.md` for KPIs and design vs non-design regions.

## Cantilever demo setup (tertiary / regression)

- Use a **rectangular beam** along X with root fixed at `x = 0` and tip load at `x = L`.
- Keep meshes **coarse** (for example max element size 6–10 mm on a 100 mm beam).

### Recommended cantilever geometry

- Length `L = 100 mm`
- Width `b = 20 mm`
- Height `h = 5 mm`
- Tip force `F = 100 N` in the -Z direction
- Material: structural steel approximation `E = 210 GPa`, `nu = 0.3`

### Analytical check (Euler-Bernoulli)

For a tip-loaded cantilever, maximum bending stress at the root outer fiber is:

`sigma_max = 6 * F * L / (b * h^2)`

With the demo numbers:

`sigma_max = 6 * 100 * 100 / (20 * 5^2) = 120 MPa`

Tip deflection:

`delta = F * L^3 / (3 * E * I)` where `I = b * h^3 / 12`

## Workflow tools in this companion

1. `create_brake_pedal` — brake pedal with solid/xtruss/fcc web; STEP/STL; FreeCAD GUI.
2. `create_engine_mount` — L-bracket with solid/bcc/fcc web; STEP/STL; FreeCAD GUI.
3. `get_lattice_metrics` — relative density, volumes, mass (pedal or mount).
4. `compare_brake_pedal_variants` / `compare_mount_variants` — solid vs X-truss/BCC vs FCC KPI table + SF recommendation.
5. `create_cantilever` — builds a `Part::Box` in FreeCAD, exports STEP/STL, opens FreeCAD GUI.
6. `apply_load_and_solve` — Gmsh mesh + CalculiX (`ccx`) for current geometry.
7. `get_max_von_mises` — latest max stress in MPa (plus SF / analytical reference when present).
8. `open_in_freecad` — re-opens the latest document in FreeCAD GUI.

## GUI visibility / camera

On launch, the companion runs `companion/macros/show_fit.py` so FreeCAD:

- unhides CAD + FEM objects (mesh, constraints, CalculiX pipeline)
- switches toward the FEM workbench when available
- sets an isometric/axonometric camera and fits all

If something still looks blank, click `Pipeline_CCX_Results` in the model tree.

## Qt “Incompatible processor … neon crc32”

This abort can happen when `FreeCADCmd` is launched from a **restricted sandbox** that blocks CPU-feature probes (return code often `-6`).

Fix: start the companion from a normal terminal:

```bash
./scripts/run_demo.sh
```

If FreeCAD still aborts, the companion falls back to precomputed / estimated KPIs (or Euler-Bernoulli ~120 MPa for the cantilever).
