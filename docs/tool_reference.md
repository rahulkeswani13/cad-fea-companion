# Companion tool reference

Compact index of every companion tool the agent can call (see `TOOL_SPECS` in
`companion/tools/cad_fea.py` for the authoritative list). Geometry tools
`create_brake_pedal`, `create_cantilever`, and `create_uav_arm` create
geometry; `get_max_von_mises` returns max stress from the latest solve.

## Geometry / authoring

- `create_brake_pedal` — create the brake-pedal lattice bracket
  (web_type solid|xtruss|fcc), export STEP/STL. Optional `material`
  (default Al 6061-T6; see `docs/materials.md`).
- `create_cantilever` — create a rectangular cantilever beam (mm). Optional
  `material` (default Steel-Generic).
- `create_uav_arm` — F26 flagship: create the quadcopter arm (clamp boss +
  tapered arm + motor ring; web_type solid|xtruss, arm_length_mm 120–320,
  cell_size_mm 6–30, strut_radius_mm 1.5–4.0). Optional `material`
  (default Al 6061-T6).
- `get_design_program` — read the persisted design program (source of truth)
  for a part: params, revision, params hash.
- `update_design_program` — edit program params and rebuild in one step
  (e.g. "set cell size to 12", "switch to titanium" via
  `changes={"material": "ti6al4v"}`); failed rebuilds preserve the accepted
  revision.

## Simulation / analysis

- `apply_load_and_solve` — mesh (Gmsh) + CalculiX solve in FreeCAD for the
  active part; falls back to precomputed/analytical KPIs. Every solve carries
  `expected_vs_actual` (pre-flight analytical estimate + divergence flag),
  a `run_id`, and a run-history record.
- `run_convergence_study` — mesh convergence study: 2–3 live CalculiX solves
  at refining mesh sizes (default 1.0x/0.7x/0.5x ladder of the part default),
  recommended mesh = coarsest within 5% of the finest max von Mises;
  synchronous/headless, costs 2–3 solves, refuses non-live setups (fcc pedal
  precomputed KPIs, FreeCAD absent).
- `get_max_von_mises` — max von Mises stress (MPa) from the latest solve.
- `query_results` — query per-run solve history: latest run in full (mass,
  max von Mises + location, deflection, mesh size, method flag) plus recent
  runs; `run_id=` returns one run.
- `get_lattice_metrics` — relative density, volumes, mass for the current
  lattice geometry.
- `compare_brake_pedal_variants` — solid vs lattice KPI comparison with a
  lightest-with-SF>=1.5 recommendation (SF judged against the program
  material's yield).
- `compare_materials` — F09 material trade-off: every table material
  (Al 6061-T6, Al 7075-T6, Ti-6Al-4V, PA12, Steel-Generic) with mass, stress,
  SF vs its own yield, and scaled deflection, ranked lightest at SF>=1.5.
  Scales the best available base run (session -> run history -> precomputed,
  labeled) linear-elastically; every row carries citation sources; PA12
  deflection is flagged not verified.

## Viewing

- `open_in_freecad` — launch the FreeCAD GUI with the latest CAD/FEM document.
