# UAV arm (F26) — geometry, design space, and load case

Parametric quadcopter arm: root clamp boss + tapered arm + tip motor-mount
ring. Generator: `companion/tools/uav_arm.py`; program params:
`web_type` (solid|xtruss), `arm_length_mm`, `cell_size_mm`,
`strut_radius_mm`, `material` (default Al 6061-T6).

## Anatomy (mm, arm along +X, thrust/load along Z)

| Feature | Value |
|---|---|
| Clamp boss | 36 × 28 × 20, four M3 bolt holes (⌀3.2) at x = 8/28, y = ±9 |
| Tapered arm | root section 24 × 12 → tip 16 × 8 over `arm_length_mm` (default 180) |
| Motor ring | OD 34 / ID 26 / thickness 8; four M3 holes at 15 mm radius, 45° spacing |
| Ring overlap | ring OD bites 5 mm into the arm tip so the fuse is seamless |
| Chord rails (xtruss) | 1.5 mm solid top + bottom rails following the taper |
| Web bite | strut ends bite 0.5 mm into the rails; rails engage the boss 2 mm |

## Design vs non-design

- **Non-design (always solid):** the clamp boss, the motor ring, and the chord
  rails. These are the mounting interfaces and the minimum-thickness faces —
  they carry loads into/out of the part and must stay smooth.
- **Design space:** the tapered interior between the chord rails. In the
  `xtruss` variant this is filled with the X-truss web (2.5D: diagonals in the
  X-Z bending plane, extruded through Y at the root width); in `solid` it is
  fully material.

The chord-rail pattern was chosen over the alternatives by iteration:
skin-enclosed lattice is invisible (indistinguishable from solid), and a bare
open truss leaves bumpy sawtooth top/bottom surfaces. Rails give smooth,
load-bearing minimum thickness on the faces while the X-pattern stays exposed
on the sides — visible without a section view.

Mass progression at the default 180 mm arm, Al 6061-T6:
solid 157 g → chord rails + X-truss web **130 g** (**~−17%**).

## Load case (F26 demo)

- **Fixed:** the four clamp-bolt cylinder faces + the boss −X mounting face
  (the face against the center plate).
- **Load:** the motor-ring top annulus faces, force +Z (thrust up),
  **120 N** default.
- F07 pre-flight: cantilever from the boss face, tip load at the ring center,
  bending at the root section (24 × 12) — conservative because the taper only
  thickens toward the root. Golden solid solve at 120 N / 3.5 mm: max von Mises
  44.6 MPa at (218.4, 9.4, 4.0) mm, tip deflection 1.69 mm, SF ≈ 6.2.

## Mesh guidance

- `solid`: 3.5 mm max element size (golden run: 4,180 nodes, solves in
  seconds).
- `xtruss`: use ~5.0 mm. The boolean of rails + strut intersections makes
  Gmsh hang at 3.5 mm (observed 30+ min single-core burn); 5.0 mm resolves
  the 1.8 mm struts coarsely but honestly — the payload's note says coarse
  tets under-predict peak strut stress.

## Artifacts

`data/exports/uav_arm_{solid,xtruss}.{step,stl}` (STEP is the primary
artifact), `data/workspace/uav_arm_{variant}.FCStd`, FEM documents at
`data/workspace/uav_arm_{variant}_fem.FCStd`. Goldens:
`data/results/uav_arm_{solid,xtruss}_precomputed.json` (solid = live
`calculix_ccx`; xtruss = `precomputed_demo_estimate` fallback, 130 g /
95 MPa / SF 2.9, because the lattice boolean hung Gmsh).
