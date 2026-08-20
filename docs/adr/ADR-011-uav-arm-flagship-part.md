# ADR-011: UAV arm flagship part (F26)

Status: accepted — 2026-08-17

## Context

F26 adds the first flagship demo part: a parametric quadcopter arm (root clamp
boss + tapered arm + tip motor-mount ring) with solid and lattice variants.
The brake pedal stays the onboarding part; the arm carries the "real mechanical
drama" demo. It slots into the table-driven spine (design programs, run
history, part-keyed dispatch), so the decisions below are about its param
surface and its geometry architecture, not the plumbing.

Live finding that forced a decision: the xtruss boolean (chord rails + strut
intersections) makes Gmsh run 30+ minutes at the solid variant's 3.5 mm mesh
size on this machine — the solid at the same size solves in seconds.

## Decision

1. **Param surface** (design program rows, `design_program.py`):
   - `web_type`: **solid | xtruss only.** `fcc` is deliberately out — the pedal
     already demos fcc, and the arm's tapered pocket adds nothing to that
     story. Additive later if a second lattice architecture earns its tokens.
   - `arm_length_mm` 120–320 (default 180): editable so "make the arm longer"
     is a one-line program edit; the bbox warn-check scales with it.
   - `cell_size_mm` 6–30 (default 12), `strut_radius_mm` **1.5**–4.0 (default
     1.8). The 1.5 mm strut floor is the meshable minimum — below it Gmsh
     cannot resolve the bar cross-section against the cell size.
2. **Chord rails, exposed web.** The xtruss variant carries 1.5 mm solid rails
   along the taper's top and bottom faces (non-design), with the X-truss web
   exposed on the sides between them. Rejected: skin-enclosed lattice (the
   lattice is invisible — looks identical to solid) and open truss without
   rails (bumpy sawtooth top/bottom surfaces). Strut ends bite 0.5 mm into the
   rails and the rails bite 2 mm into the boss for clean fuses.
3. **Design vs non-design:** boss, motor ring, and chord rails are non-design
   solid; the tapered interior between the rails is the lattice design space.
   This is the map `docs/uav_arm_lattice.md` documents and the demo narrates.
4. **Mesh sizing per variant:** `DEFAULT_MESH_MM = 3.5` for solid; xtruss
   solves need ~5.0 mm — the boolean complexity of rails + strut intersections
   chokes Gmsh at 3.5 (observed 30+ min single-core burn, killed). The FEM
   script's node-count guard (25k) bounds the damage if a size is too fine.
5. **Goldens + calibrated fallback.** Committed CalculiX runs live in
   `data/results/uav_arm_{solid,xtruss}_precomputed.json` (120 N, Al 6061-T6,
   live `calculix_ccx`). `fallback_fea_result`'s base pairs (max VM, tip
   deflection at the 120 N reference) are calibrated on those goldens, not
   guessed; stress scales with force, deflection with force and inverse
   modulus, and the payload says `precomputed_demo_estimate` with `fallback:
   true`.
6. **Orphan-mesh guard (spine fix riding along):** `run_freecad_python` now
   launches FreeCADCmd in its own process group and kills the group on
   timeout, so a hung solve can no longer orphan a 100%-CPU Gmsh child.

## Consequences

- The router, `KNOWN_PARTS` corrections, and `compare_materials`/
  `load_precomputed_results` ladders treat uav_arm as a first-class part; no
  existing tool contract changed (additive rows and dispatch branches only).
- `create_uav_arm` is a HITL-gated mutating tool like the other creates.
- Solver honesty unchanged: every arm answer states method (calculix_ccx /
  precomputed_demo_estimate / analytical), mesh size, and that coarse tets
  under-predict peak strut stress; lattice solves compare against the
  solid-section F07 estimate with the explicit caveat key.
- Verification: `tests/test_uav_arm.py` (16 memory-only tests), UAV routing
  tests in `tests/test_pedal_heuristics.py`, five `f26_*` eval cases,
  `docs/uav_arm_lattice.md`, and a `Features.md` talking script.
