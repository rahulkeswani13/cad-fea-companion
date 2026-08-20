# ADR-010: Material as program parameter (F09)

Date: 2026-08-16 · Status: accepted

## Context

F09 makes material a first-class parameter: "compare Ti vs Al" end-to-end with
citations, and "switch the pedal to titanium" as a program edit. The design
was settled in a grill-me review (2026-08-16) over two rounds.

Before F09, material was hardcoded in ~6 places: `brake_pedal.py` Al
constants (density/E/nu/yield) baked into the geometry script, FEM material
card, and every fallback/precomputed result; cantilever steel hardcoded twice
(analytical E, `Steel-Generic` FEM card) and listed as a *read-only* fixed
constant of its design program; `compare_brake_pedal_variants` always judged
SF against Al yield. Embedding RAG (F15) is scheduled *after* F09, so
"RAG-grounded" could not mean embeddings yet.

## Decisions

1. **Cited static table, not embeddings.** Source of truth:
   `data/materials.json` — five materials (Al 6061-T6, Al 7075-T6,
   Ti-6Al-4V, PA12, Steel-Generic), each property traced to a source string
   (MatWeb/MMPDS/EOS/FreeCAD card). `docs/materials.md` mirrors the numbers
   so the existing TF-IDF RAG store (`companion/rag/store.py` ingests
   `docs/**/*.md`) can cite them in chat; `tests/test_materials.py::test_docs_materials_md_stays_in_sync`
   asserts the two cannot drift. F15 will wrap the same table, not replace it.
2. **Material is an editable design-program param** (enum-validated against
   the table, like `web_type` — not a numeric range). "Switch to Ti" =
   `update_design_program(changes={"material": "ti6al4v"})`: alias
   normalization (`ti`, `ti64`, `Ti-6Al-4V`, `nylon`, `7075`, `s235` all
   resolve), rev bump, rebuild with the new density/E/nu/yield, failed
   rebuild preserves the accepted revision (F04 rules unchanged). **Contract
   touch:** the cantilever's `material` moved from `FIXED_CONSTANTS` to an
   editable param; per-part defaults (`al6061t6` pedal / `steel` cantilever)
   keep every pre-F09 caller byte-identical (default Al result strings are
   unchanged). Legacy on-disk programs self-heal: an edit re-commits them
   with their implicit default material.
3. **Compare = one base run + linear-elastic scaling, honestly labeled.**
   `compare_materials` scales the best available base run per material:
   stress unchanged (E-independence assumption — approximate for the
   lattice), deflection × E_ref/E_new, mass × ρ_new/ρ_ref, SF vs each
   material's room-temperature yield. Method labels: `scaled_from_calculix`
   / `<base>_scaled`. Base-result ladder (labeled in the payload): session
   solve → latest F06 run-history record → committed precomputed KPIs →
   brake-pedal demo estimate; the cantilever refuses (`no_results`) instead
   of guessing. Ranking: lightest mass at SF ≥ 1.5, mirroring
   `compare_brake_pedal_variants`.
4. **PA12 policy: include, flag, don't fabricate.** The PA12 row appears in
   comparisons (mass/SF are usable), but its scaled deflection carries
   `deflection_not_verified: true` — at E ≈ 1.8 GPa linear scaling leaves
   the small-strain regime; the correction says to run a live solve.
5. **Solver honesty stays in band.** Yield = room-temperature Rp0.2
   handbook values. Not-verified notes cover fatigue, temperature,
   moisture uptake (PA12), and as-built AM lattice allowables — no
   knockdown factors in F09. Cost is a 3-class label, not a model.

## Consequences

- Both parts take `material` (default preserves behavior); the UAV arm (F26)
  inherits the table for free. The pedal's demo deflection fallback now
  scales with the target modulus (Al-calibrated base × E ratio).
- `create_brake_pedal` / `create_cantilever` / `update_design_program` /
  `apply_load_and_solve` accept and propagate material; `TOOL_SPECS`,
  the LangChain tool schemas, and the heuristic router (material phrases →
  `compare_materials`; "switch to X" → `update_design_program`) registered it.
- Verification: `tests/test_materials.py` (20 tests: aliases, citations,
  byte-identical defaults, scaling math, PA12 flag, program transaction,
  compare ladder/refusal, legacy self-heal, docs sync) and eval cases
  `rag_materials_table`, `f09_compare_materials`,
  `f09_set_material_7075_dry_run`, `f09_unknown_material_rejected`.
- Out of scope, deliberately: embedding retrieval (F15), temperature/fatigue
  knockdowns, as-built AM property correction, cost modeling, multi-material
  single solves (one material per part), live per-material re-solve mode.
