# ADR-009: Mesh convergence study (F08)

Date: 2026-08-16 · Status: accepted

## Context

The plan's P0 spine ends with F08: mesh convergence automation
(`run_convergence_study`, 2–3 densities, recommendation) so docs and answers
can always state a mesh size with evidence. The design was settled in a
grill-me review (2026-08-16) with four decisions: live solves only, von
Mises as the metric with a 5% band against the finest run, a fixed
multiplier ladder with explicit override, synchronous execution. This ADR
records them plus what stayed out of scope.

The trap the design avoids: the FCC pedal variant returns precomputed demo
KPIs and the no-FreeCAD path returns analytical fallbacks — neither varies
with mesh size, so a "convergence table" there would be fabricated evidence.

## Decisions

1. **Live-solves-only gate.** The study refuses up front (F02 envelope:
   one error + one correction) when the active setup cannot produce
   mesh-varying solves: fcc pedal → new `unsupported_setup` error class;
   FreeCAD absent → `freecad_missing`. A mid-study sub-run that falls back
   (`method != calculix_ccx` or `fallback` flag) is recorded as a failed
   mesh, not silently mixed into the table.
2. **Metric + verdict.** Max von Mises is the convergence metric;
   pad/tip deflection is reported as context only. Recommendation = the
   **coarsest** mesh whose max von Mises is within 5% of the finest run's
   value — the cheapest mesh that buys the converged answer. If no coarser
   mesh qualifies, the report says not-converged, offers the finest mesh as
   best-available, and flags "refine further". No Richardson extrapolation.
3. **Mesh ladder.** Default = fixed multipliers (1.0 / 0.7 / 0.5) of the
   part's default mesh size (pedal 5/3.5/2.5 mm, cantilever 2.5/1.75/1.25
   mm); `mesh_sizes_mm` (2–4 distinct positive entries) overrides it.
   Geometry-aware ladders (tied to strut radius / cell size) wait for F26's
   part family.
4. **Synchronous, headless, history-native.** Sub-runs go through
   `apply_load_and_solve` with `open_gui=False`, so each is an ordinary F06
   run-history record and the report cites `run_id`s. A failed mesh makes
   the study `incomplete` (partial report) rather than aborting silently;
   all-failed returns a failure envelope carrying the last failure's class.
   Async handles are F11's job. The session ends on the finest run's
   result, exactly as if the solves had been issued by hand — the
   recommendation itself mutates nothing (mesh stays a per-call argument).

## Consequences

- "Is this mesh-converged?" is now answerable with live evidence, and the
  cross-cutting rule "docs always state mesh size" has a tool that decides
  *which* size to state (R3/R6).
- New `unsupported_setup` correction added to `outcome.CORRECTIONS`
  (additive); `outcome.condense_error` exposed as a public alias for
  condensing sub-run errors.
- Registered at all three tool points (TOOL_SPECS, dispatcher, LangChain
  tools), added to `FREECAD_MUTATING_TOOLS` (it spawns FreeCAD solves), and
  the heuristic router routes convergence/mesh-sensitivity phrases.
- Verification: `tests/test_convergence.py` (13 memory-only tests: refusals,
  ladder/validation, converged + not-converged verdicts, headless sub-runs,
  fallback/failure honesty, router phrases) and eval cases
  `f08_convergence_fcc_refused` (deterministic refusal) +
  `agent_mesh_convergence` (agent routes to the tool).
- Out of scope, deliberately: Richardson extrapolation, local/adaptive
  refinement at the peak node, auto-applying the recommended mesh to future
  solves, convergence plots, run-history schema changes.
