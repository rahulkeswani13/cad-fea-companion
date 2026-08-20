# ADR-003: Pre-mesh B-Rep validation gate (F03)

Date: 2026-08-16 · Status: accepted

## Context

Invalid geometry previously surfaced as a Gmsh/CalculiX crash deep in the solve:
the only B-Rep check was a final `isValid()` at the end of `build_pedal_body`,
reported as a raw `RuntimeError` with no stage, no check details, and a generic
error class. The FEM scripts' sanity checks (node counts) run *after* meshing —
too late and billed in mesh time.

## Decisions

1. **Two-layer gate in `companion/tools/validate.py`.** Host-side
   `validate_geometry_payload(params)` rejects degenerate params (≤ 0, NaN,
   non-numeric) before FreeCADCmd ever launches — deterministic and
   memory-testable. FreeCAD-side `companion_validate_brep(body, expected_vol,
   rho)` is injected into all four generator scripts (both parts × geometry +
   FEM) immediately after the body is recomputed and BEFORE any STEP/STL export
   or Gmsh meshing.
2. **Hard vs soft split.** Hard (block): `shape_null`, `brep_invalid`,
   `volume_nonpositive`, `bbox_degenerate`. Soft (warn only): volume vs the
   host's independent estimate within [0.5×, 1.5×], relative density in
   (0, 1.05] — boolean fuzz must never block a demo. Soft findings ride as
   `validation.warnings`. `not (x > 0)` idioms catch NaN without isfinite.
3. **Named stage in the payload, one class in the envelope.** Successes carry
   `validation: {stage: "passed", checks, warnings}` (additive key); failures
   early-print the COMPANION_JSON payload and exit before mesh/solve, mapping
   to the new additive F02 error class `geometry_invalid` with one concrete
   correction. Stage carries granularity; the class stays coarse.
4. **Early exit mechanism:** print marker → `sys.stdout.flush()` →
   `raise SystemExit(0)`. The flush is load-bearing: FreeCADCmd's embedded
   interpreter can drop buffered stdout on SystemExit (found by the null-shape
   probe test). SystemExit is a BaseException, so the scripts' `except
   Exception` does not swallow it.
5. **Scope guardrails.** Host gate checks degenerate values only — per-part
   min/max ranges belong to F04's design-program preflight. Both parts are
   wired identically; per machine-safety constraints, runtime tests and evals
   exercise brake pedal only (mount wiring is covered by script-content and
   compile tests).

## Consequences

- Invalid B-Rep costs seconds, not a meshing run, and reports a named stage
  with check details (OCC error strings included) through the F02 envelope.
- All future generator scripts should reuse `FREECAD_VALIDATION_SNIPPET` +
  `gate_call_snippet(part, expected_vol)` (one interpolation each).
- Eval runner gained `expect_validation_stage`; new case
  `f03_nonpositive_strut_rejected` is deterministic with and without FreeCAD.
