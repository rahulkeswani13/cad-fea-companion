# ADR-006: Run history + result querying (F06)

Date: 2026-08-16 · Status: accepted

## Context

Solves were fire-and-forget: the latest result lived in the per-thread
session and one overwriting JSON per part (`<part>_<web>_precomputed.json`
under workspace/), with no run identity, no location for the stress peak,
and no way to answer "what changed between runs" from stored state. ADR-004
explicitly deferred per-run artifacts here. F06 calls for per-run history and
a `query_results` tool. Decisions were stress-tested in a design review
(grill-me, 2026-08-16); implementation and live verification were scoped to
the brake pedal.

## Decisions

1. **History = append-only JSONL per part** (`data/workspace/<part>_runs.jsonl`,
   one solve = one line), shared across chat threads like the design
   programs. No rotation/compaction at demo scale; reads are tail-limited
   (`last_n`, capped at 50). A database is overkill until F11.
2. **Every solve invocation is recorded**, including fallback/precomputed
   ones — their `method` flag (`calculix_ccx` / `precomputed_demo_estimate`
   / `analytical_euler_bernoulli`) keeps the record honest. Recording
   degrades to a `history_write_error` warning key and can never fail a
   successful solve (mirrors `_record_program`).
3. **`run_id` = UTC timestamp + 6-hex random suffix** (sortable, unique);
   it is stamped into the solve payload, so result → history → query share
   one identity. Records also carry the design program's `rev`/`params_hash`
   at solve time.
4. **Max-VM location captured for the brake pedal only** (F06 scope): the
   FEM script finds the peak-von-Mises node and reports its (x, y, z) in the
   part frame as `max_vm_location_mm`. Location is best-effort — `null`
   when the result object cannot be mapped onto mesh nodes (and on
   fallback/precomputed runs, which have no mesh).
5. **Reaction forces deferred to F10.** CCX only emits them via the `.dat`
   file with an input-deck tweak — a parsing rabbit hole for marginal demo
   value until BCs become program params. `query_results` states
   "reactions: not captured" instead of returning blanks.
6. **`query_results` contract:** `{part?, run_id?, last_n?=10}`. Default
   returns the latest run in full + compact rows (newest first); `run_id`
   returns that single run. "Where is stress concentrated" is the agent
   reading `max_vm_location_mm` — no NL parsing inside the tool. Registered
   at all three points (TOOL_SPECS, `_call_tool_raw`, LangChain tools),
   avoiding the design-program tools' registration asymmetry. Read-only —
   no HITL gate.

## Consequences

- "Where is stress concentrated" and "what changed between runs" are
  answerable from stored state across restarts; `get_max_von_mises` remains
  untouched (additive surface).
- The solve payload's `expected_vs_actual` block (ADR-007) is attached
  before the record is written, so run records carry the expected value,
  ratio, and divergence flag of their solve.
- Verification: `tests/test_run_history.py` (12 memory-only tests), eval
  cases `f06_solve_pedal_records_run`, `f06_query_results_latest`,
  `f06_query_results_bad_run_id`, `f06_query_results_unknown_part`,
  `agent_where_stress_concentrated` (deterministic with and without FreeCAD
  via the fallback path), plus a live brake-pedal solve on this machine
  validating location capture (23.7 MPa at (18.4, 100.0, 10.4) mm).
