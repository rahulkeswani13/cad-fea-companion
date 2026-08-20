# ADR-002: Tool outcome envelope (F02)

Date: 2026-08-16 · Status: accepted

## Context

Every tool returned an ad-hoc dict, and three paths leaked raw diagnostics into
LLM context: FreeCAD scripts embed `traceback.format_exc()` into `error`;
`run_freecad_python` failures carry `stdout_tail`/`stderr_tail` (2,000 chars
each) into results; `node_tools` serializes the whole result into the
`ToolMessage`. On top of that, `get_max_von_mises` returned its KPIs three
times over (top level + `geometry` + `full_results`), and the system prompt
re-serialized full geometry/results every turn. Failures gave the agent no
machine-readable class and no suggested next action.

## Decisions

1. **Flat-additive envelope, not a nested `data` wrapper.** Existing keys keep
   working; we add `receipt` (always) and on failure `error_class` +
   `correction` (+ `debug_ref` when raw output was moved to the log). A nested
   restructure would break four consumers (eval runner, tests, workspace-JSON
   reload path, graph state mirroring) for zero LLM benefit.
2. **Single choke point.** `companion/tools/outcome.py::wrap_tool_call` wraps
   `cad_fea._call_tool_raw` via `call_tool`; the HITL-cancel result in the
   graph and the `/api/results/load_precomputed` endpoint envelope explicitly.
   Injected test tool functions (`call_tool_fn`) are intentionally not wrapped.
3. **Small failure taxonomy now; F13 extends.** 11 classes (`bad_params`,
   `unknown_tool`, `no_geometry`, `no_results`, `freecad_missing`,
   `freecad_timeout`, `freecad_crash`, `mesh_failed`, `solve_failed`,
   `internal_error`, `user_cancelled`), each with exactly one concrete
   correction in `outcome.CORRECTIONS`. Tools may override via an explicit
   `error_class`/`correction` key; otherwise `classify_error` maps the message.
4. **Raw diagnostics go to disk, not chat.** Tails, tracebacks, and errors
   over 300 chars are moved to `data/workspace/logs/tool_debug.log` and
   referenced by `debug_ref` — keeps root-cause capability without polluting
   context. Unexpected tool exceptions become `internal_error` failures
   (tools can no longer crash the graph node) with the traceback in the log.
5. **Receipts are `{tool, elapsed_s, changed}`.** Units stay encoded in key
   names (`_mm`, `_n`, `_mpa`); KPIs are not duplicated into the receipt.
   `changed` records session state transitions (`geometry_replaced`,
   `results_replaced`) detected by identity compare in the wrapper.
6. **Context compaction:** the system-prompt CAD blob now carries a KPI-only
   summary; `get_max_von_mises` dropped its `geometry` and `full_results`
   echo keys — the only surface removals in this ADR (nothing consumed them;
   the eval runner reads the top-level KPI first).
7. **`eval/cases.json` is canonical** (not `cases.jsonl`); the runner gained
   `expect_error_class` / `expect_correction` / `expect_receipt` checks.

## Consequences

- All future tools (F03+) must flow through the envelope — wrapping happens
  automatically for anything dispatched via `call_tool`.
- No raw tracebacks or stdout/stderr tails can reach the LLM; the test suite
  enforces this (`tests/test_outcome.py`).
- Known pre-existing eval gaps (not F02): `tool_solve*` expectations assume
  the analytical-fallback path when FreeCAD is installed (live coarse-mesh
  CalculiX under-predicts); `rag_workflow_tools` retrieval misses on the
  current corpus.
