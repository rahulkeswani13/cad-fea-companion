# ADR-005: Skip F05 (frozen workbench)

Date: 2026-08-16 · Status: accepted

## Context

F05 planned an "active-domain" in graph state with per-turn tool filtering:
authoring tools (create/update) vs analysis tools (solve/compare), so the
agent would not offer solves before geometry exists. Reviewing the P0 spine,
the failure it guards against is already covered cheaply — every analysis
tool already returns a structured `no_geometry` failure with one correction
("call create_* first") through the F02 envelope, and the heuristic router
already scopes mount/pedal phrasings.

## Decision

Skip F05. Revisit before F17 (freeform workbench), which lists F05 as a
dependency because agent-authored FreeCAD Python raises the stakes of
tool scoping. F06/F07 depend only on F02/F04 and proceed regardless.

## Consequences

- All tools remain offered every turn; the no-geometry guard stays at the
  tool-call boundary (envelope correction), not the router.
- PLAN.md F05 row is annotated as skipped (2026-08-16, this ADR).
- No code was removed — F05 was never implemented.
