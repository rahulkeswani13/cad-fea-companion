# ADR-013: Canonical pydantic tool schemas (schemas, ranges, boundary validation)

Date: 2026-09-01 · Status: accepted

## Context

The hardening review found three sources of truth for one concept — a tool's
parameters:

1. hand-written prose in `TOOL_SPECS` (what the LLM sees);
2. pydantic arg models in `agent/tools.py` that shaped `bind_tools` calls but
   carried ranges **in prose only** (`"arm_length_mm: float (120-320)"`), with
   no machine-enforced constraint;
3. `design_program.PARAM_SPECS` numeric floors, enforced by
   `update_design_program` preflight alone.

Consequence — the guardrail gap: a `create_*` call with out-of-range args
(e.g. `strut_radius_mm: 0.8` on the UAV arm, below the 1.5 mm meshable floor)
bypassed preflight entirely and reached the generator/F03 gate, which only
catches *degenerate* geometry, not out-of-envelope designs. The eval suite's
adversarial cases encoded exactly this hole.

## Decisions

1. **The pydantic models are the single source of truth.** They move to
   `companion/tools/tool_schemas.py` (dependency-free, so both the agent and
   tools packages can import them without cycles) and gain real
   `Field(ge=, le=)` constraints copied from the program floors.
   `agent/tools.py` re-exports the models — its public import surface is
   unchanged.
2. **`TOOL_SPECS` is generated** from a `TOOL_REGISTRY` of
   (name, description, args model); the `parameters` block of each spec is the
   model's JSON schema (defaults, enums, minima/maxima included). Prompt text
   and wire format can no longer disagree with the models. H11 freezes this
   output as a contract snapshot.
3. **`call_tool` validates args against the models before dispatch.**
   Out-of-range `create_*` args hard-reject as `error_class: bad_params` with
   one correction — ADR-004's never-clamp philosophy, now enforced at the
   boundary, not just the program-update path. Rejections carry the standard
   receipt (elapsed 0.0) so the eval contract (`expect_receipt`) holds.
4. **`PARAM_SPECS` is a derived view** (`numeric_param_ranges()` reads the
   `ge`/`le` metadata off the same models). Program floors and call-time
   validation cannot drift; `design_program.preflight` semantics are
   unchanged.

## Consequences

- Eval cases that asserted the gap (`adv_cantilever_negative_length`,
  `adv_cantilever_zero_height`, `f03_nonpositive_strut_rejected`) now expect
  `bad_params` at the boundary; a new `adv_uav_arm_strut_below_floor` case
  pins the 0.8 mm floor rejection. The F03 B-Rep gate remains the second
  layer for in-range-but-degenerate geometry (tested at function level).
- Error strings for schema violations come from pydantic (e.g. `Input should
  be 'solid', 'xtruss' or 'fcc'`) instead of the hand-written
  `must be one of ...`; the contract stays `error_class` + `correction`.
- Adding a tool parameter is now one edit on one model: schema, LLM-visible
  spec, boundary validation, and (for numeric geometry params) the program
  floor all update together.
