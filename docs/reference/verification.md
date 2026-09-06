# Verification and evidence limits

Solve results identify their method and mesh size when applicable. Answers should
repeat those fields and state what remains unverified. A result can be useful for comparison while
still being a fallback, a coarse mesh, or an analytical reference.

## Solve methods

| Method | Meaning | Applicability and limits |
|---|---|---|
| `calculix_ccx` | Live Gmsh tetrahedral mesh followed by a linear-static CalculiX solve | Mesh-dependent result. Coarse tetrahedra can under-predict peak stress, especially in lattice struts. |
| `analytical_euler_bernoulli` | Closed-form cantilever bending reference | Applies to the rectangular cantilever idealization; it is not a 3D bracket solve. |
| `precomputed_demo_estimate` | Stored or calibrated demo KPI used when a live solve is unavailable | Labeled fallback, not a new mesh solve. FCC pedal and unavailable-FreeCAD paths cannot support mesh convergence. |

The cantilever reference uses
`sigma_max = 6 F L / (b h^2)` and
`delta = F L^3 / (3 E I)`, with `I = b h^3 / 12`. For the default
`100 × 20 × 5 mm` beam at `100 N`, the analytical maximum bending stress is
`120 MPa`. This is a reference calculation under the stated geometry, load, and
material assumptions.

## Expected versus actual

Each successful solve adds an `expected_vs_actual` block where an analytical
beam idealization is available. It records the expected stress, actual stress,
ratio, the `[0.33, 3.0]` divergence band, assumptions, and a divergence flag.
For lattice variants the estimate assumes the corresponding solid section and
is explicitly a caveat; it does not block or certify the solve. Missing or
non-finite actual stress leaves the ratio and flag unset.

## Mesh convergence

`run_convergence_study` requires live, mesh-varying CalculiX solves. The default
coarse-to-fine ladder is `1.0×`, `0.7×`, and `0.5×` the part default mesh
(pedal `5/3.5/2.5 mm`; cantilever `2.5/1.75/1.25 mm`); an explicit list may
contain 2–4 distinct positive mesh sizes. The primary metric is maximum von
Mises stress; deflection is context only.

The recommended mesh is the coarsest run within 5% of the finest run's maximum
von Mises value. If none qualifies, the report is `not converged`, offers the
finest run as best available, and says to refine further. A failed or fallback
sub-run is recorded and makes the report incomplete. FCC pedal precomputed KPIs
and analytical fallback solves are refused because they do not vary with mesh
size. The study is synchronous and each successful sub-run has a `run_id` in
per-part JSONL history.

## Stored evidence

`query_results` returns the latest run and compact recent rows with `run_id`,
method, mesh size, stress, safety factor, and (when mapped) peak-stress
coordinates. Reaction forces and local/adaptive refinement around the peak are
not captured. Material values in `docs/reference/materials.md` are bulk,
room-temperature reference values; fatigue, temperature, moisture, build
orientation, and production allowables remain outside this verification scope.

Source and applicability: current result fields and fallback behavior are in
`companion/tools/cad_fea.py`, `companion/tools/estimate.py`,
`companion/tools/convergence.py`, and `companion/tools/run_history.py`; the
analytical and convergence policies are ADR-007, ADR-006, and ADR-009. These
checks support engineering review and comparison, not certification of part
safety.
