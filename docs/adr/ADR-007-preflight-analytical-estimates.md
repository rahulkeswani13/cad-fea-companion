# ADR-007: Pre-flight analytical estimates (F07)

Date: 2026-08-16 · Status: accepted

## Context

Only the cantilever had a closed-form reference (`analytical_cantilever_stress`,
attached post-solve); the pedal and mount solved with no expectation to judge
the result against, so a mesh artifact or setup error would surface as a
confident-looking number. F07 calls for a pre-flight analytical estimate on
every solve with an expected-vs-actual divergence flag. Decisions come from
the same design review as ADR-006 (grill-me, 2026-08-16); implementation and
live verification were scoped to the brake pedal.

## Decisions

1. **Idealization per part, assumptions stated in the payload:**
   brake pedal = overhang cantilever from the clevis ring (L≈122 mm,
   36×15 mm section, ≈45 MPa at 500 N — conservative vs the pivot support);
   engine mount = axial compression through the upright (F/A ≈ 27.8 MPa at
   20 kN); cantilever = the existing Euler-Bernoulli reference
   (cross-checked equal by tests). Calibration against live solves:
   pedal xtruss ≈ 23.6 MPa (ratio 0.52), mount bcc ≈ 33 MPa (ratio 1.19).
2. **Divergence band [0.33, 3.0] on actual/expected, annotate only.** Beam
   idealizations of real brackets are legitimately off by that much (holes,
   coarse tets); the flag prompts a re-check of mesh and assumptions, never
   blocks or rewrites a result. Lattice variants compare against the
   solid-section estimate with an explicit `caveat` key.
3. **`expected_vs_actual` is one nested block on the solve payload**
   (expected/actual/ratio/band/flag/method/assumptions), attached before the
   workspace JSON write so stored results and F06 run records carry it.
   Missing or non-finite actuals keep the expected value and set
   ratio/divergence to `None` instead of guessing.

## Consequences

- Every solve now self-reports whether it agrees with hand-calc physics —
  the demo line for the R2/R6 JD keys.
- `estimate.py` is pure (no FreeCAD, no session state), so the idealizations
  are testable in isolation and reusable for F08 convergence checks.
- Verification: `tests/test_estimate.py` (8 tests: idealization values,
  cantilever cross-check vs the analytical reference, band edges, lattice
  caveat, missing-actual handling), eval case
  `f06_solve_pedal_records_run` asserting `expected_vs_actual` on every
  solve, and the live pedal solve (ratio 0.526, no flag).
