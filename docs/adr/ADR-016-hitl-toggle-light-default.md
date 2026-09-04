# ADR-016: Runtime HITL toggle (default on) + light-first console

Date: 2026-09-04 · Status: accepted

## Context

The FreeCAD human-in-the-loop gate (`AGENT_REQUIRE_TOOL_CONFIRM`) had two
problems. It was a **startup-only default-off flag**: the confirm decision
was read once inside `build_graph` and baked into the tools-node closure, so
changing posture required a server restart mid-demo; and the shipped default
was `false`, meaning a fresh install silently auto-ran every mutating tool.
Demo flow also assumed an operator wants the pause *sometimes* (scripted
rejection beats) but never *always-off* on a projector without friction to
turn it back on.

Separately, the React console defaulted to the warm-graphite dark theme.
Demos run on projectors in lit rooms, where the light "paper" surface reads
better; dark was the default only because it was built first.

Constraints: AGENTS.md additive-first (no tool contract changes); the
45-check legacy browser suite and the eval harness must stay green; eval and
CI run headless with no operator to approve interrupts.

## Decisions

1. **The gate is an operator control, default on.**
   `agent_require_tool_confirm` now defaults to `true`. Resolution order at
   each tool-node visit (most specific wins): explicit
   `build_graph(require_tool_confirm=...)` (test injection) → the runtime
   override (`POST /api/tool-confirm`, module `companion/agent/confirm.py`)
   → the setting. The graph resolves the decision **at tools-node visit
   time** instead of build time, so flipping the toggle affects the same
   compiled graph immediately — checkpointed thread history and mid-session
   state included. No rebuild, no reload.
2. **`POST /api/tool-confirm` `{enabled: bool}`** is the single write
   endpoint (additive; response carries `require_tool_confirm` +
   `confirm_source`). `/api/solver-status` gains `confirm_source`
   (`"runtime" | "setting"`) and `/api/health` reports the effective value;
   both are read views of the same layer. No tool schemas or `.env` *keys*
   change — only the setting's default flips, which this ADR approves.
3. **Headless consumers pin the gate explicitly.** `eval/run_eval.py` calls
   `set_require_tool_confirm(False)` at import (a sweep has no operator);
   the existing test suites keep passing `require_tool_confirm=False` to
   `build_graph`. The browser suite's mocked graph is unaffected because it
   injects the parameter.
4. **Console UI: the gate is a live switch in the solver rail** ("HITL
   gate", 05), defaulting checked; the top-bar HITL cell and solver status
   reflect the effective value after every turn. Rejection still lands as a
   `user_cancelled` outcome envelope — the audit trail shows the posture.
5. **Light theme is the console default.** The boot script applies
   `data-theme="light"` unless a stored `"dark"` preference says otherwise
   (anti-flash); the toggle state and its persistence are unchanged — dark
   becomes an explicit choice, light the out-of-box experience.

## Consequences

- A fresh install now interrupts before mutating FreeCAD tools until the
  operator flips the switch — the safe side is the default side.
- Mid-session posture changes are possible without restarts; demos can
  script a reject beat and then continue auto-running without touching
  `.env`.
- Eval/CI behavior is unchanged (pinned off); the headless eval `http` case
  type gained additive `method`/`json_body` support to gate the new endpoint
  key-less.
- Removing `companion/agent/confirm.py` or re-baking the decision at build
  time later would be a contract change needing a new ADR.
