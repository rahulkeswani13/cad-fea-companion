# AI-Engineering Hardening Plan — 5 Areas, P0→P2 (waves, ~7–8 days)

**Status:** Planned (grilled & settled 2026-09-01) · **Deliverable:** code on a feature branch — `main` untouched until manual merge

## Goal

Close every weakness from the 5-area AI-engineering review: single source of
truth for CAD state, send-time context trimming, pydantic-canonical tool
schemas with real boundary validation, eval history + retrieval metrics, and
end-to-end token metering. Three independently shippable waves.

## Workflow (settled)

- Branch **`ai-engineering-hardening`** off `main`; one **draft PR** opened at
  first push; **one commit per item** (~14 commits); `main` never touched by
  the implementer — the user merges manually when demo-solid.
- First commit extends `.github/workflows/ci.yml` push triggers to include the
  branch, so CI gates every push (PR trigger already covers review).
- Per-commit gate: CI (full pytest + browser + key-less eval). Per-wave gate:
  local full pytest + key-less eval; H7 additionally re-runs evals.

## Locked decisions (grilling rounds 1–2)

| Decision | Choice |
| :--- | :--- |
| Sequencing | **Waves**: all P0s, then P1s, then P2s |
| Range enforcement | **Hard reject** out-of-range `create_*` args at the boundary (ADR-004 philosophy: never clamp) |
| Prompt surgery | **Deep**: remove hardcoded answer figures *and* per-part defaults the prompt re-states; keep routing hints + honesty rules |
| Trimming | **Deterministic**: last ~20 messages verbatim; older ToolMessages → receipts; send-time only (checkpointed history stays full) |
| Response cache / LLM summarization / CI history artifacts | **Skipped / replaced with deterministic digest / local-only** |
| Pydantic scope | **Canonical for both** tool schemas and program ranges (`PARAM_SPECS` becomes a derived view) |
| Fact-check findings | Pydantic arg models already exist in `agent/tools.py` (ranges in prose only → add real constraints); `_STATE` writes are concentrated in `cad_fea.py` (contained refactor) |

---

## Wave P0 — correctness & cost (~3 days, commits H0–H5)

**H0 · CI branch trigger** (~10 min)
`ci.yml`: `push.branches += [ai-engineering-hardening]`. First commit on the branch.

**H1 · Send-time context trimming** (~half day)
New `companion/agent/context.py`: pure `condense_history(messages, keep_last=20)` —
older ToolMessages collapse to their receipt line (tool, ok, elapsed, KPI keys);
human/AI turns kept verbatim within the window. Applied **only when building the
LLM payload** in `node_agent` (checkpointed state untouched — multi-turn memory
claim intact). Unit tests: window math, receipt shape, "current turn never trimmed".
*Interview payoff:* "I cut LLM payload size on long sessions by N% — measured."

**H2 · Token metering, chat path** (~half day)
`GeminiProvider.complete_messages` captures `usage_metadata` → `AgentTurn.usage` →
`run_agent` result gains additive `usage` (per turn) and `/api/health` reports
per-thread session totals (module counter keyed like CAD sessions). Judge path
already demonstrates the pattern. Tests with a fake provider.
*Payoff:* every answer carries its token cost; session totals visible.

**H3 · Pydantic canonical: schemas + ranges + boundary validation** (~1 day, **behavior change**)
Promote the existing `agent/tools.py` models: add `Field(ge=, le=)` constraints
from the program floors; generate `TOOL_SPECS` JSON schemas from the models;
`call_tool` validates args against the models **before** dispatch (out-of-range
`create_*` now rejects with `bad_params` + correction — closes the discovered
guardrail gap); `design_program.PARAM_SPECS` becomes a derived view of the same
models (public API unchanged). Update the eval/README claims about the gap.
Tests: schema generation stability, boundary rejections, PARAM_SPECS derivation.
*Payoff:* "one source of truth — schemas, validation, and program floors all
derive from one model" — the strongest architecture sentence in the repo.

**H4 · CAD state: single writer** (~half day)
`_SESSIONS` (via `_STATE`) stays authoritative; `node_tools` stops mirroring
geometry/results into graph state (the dead `create_uav_arm` mirror branch dies
with it); `sync_cad_state` becomes the only graph-side writer. `run_agent` output
keys unchanged. Tests: session↔graph consistency across create/solve/multi-turn.

**H5 · Eval history + delta** (~2–3 h)
Append each report to `data/results/eval_history.jsonl`; summary prints delta vs
the previous entry (passed/failed/judge counts). Tests for delta computation.
*Payoff:* "evals trend, they don't just gate."

## Wave P1 — structure & honesty (~2.5–3 days, commits H6–H10)

**H6 · Router extraction** (~1 day)
`companion/agent/heuristics.py`: `HeuristicRouter` class owning all keyword
helpers; `settings.heuristic_fallback: bool = True` documents the offline mode;
`graph.py` calls `router.plan(...)` when no LLM or on first-visit assist.
Behavior-identical (existing agent/routing tests must pass untouched).

**H7 · Deep prompt surgery** (~half day + eval re-run)
`SYSTEM_PROMPT` loses hardcoded figures and per-part defaults (loads, mesh
sizes, stress references) — those live in tool schemas, tool defaults, and
result payloads. Keeps: role, tool-routing hints, honesty rules, CAD-state blob
slot, RAG context slot. Re-run key-less eval; flip any substring expectation to
tool-derived values; judge rubrics already check quality, not numbers.
*Payoff:* kills the "teaching to your own test" critique at the root.

**H8 · Envelope-integrated validation everywhere** (~half day)
Remaining tools returning raw-shaped errors route through the outcome envelope
classes (`bad_params` + one correction). Audit: unknown-tool, part-arg tools.

**H9 · Retrieval metrics** (~half day)
`eval/rag_labels.json`: ~20 queries labeled with expected source docs (grows the
existing 8 RAG cases); report gains `retrieval: {hit_rate_at_4, mrr}` — computed
key-less, deterministic. *Payoff:* "retrieval hit-rate 90%+ (hit@4), measured."

**H10 · UI token pill** (~1–2 h)
Status bar shows session tokens; SSE `final` event already carries data — extend
with usage. Pairs with H2.

## Wave P2 — polish (~1.5–2 days, commits H11–H14)

**H11 · Wire-format contract tests** (~half day): frozen snapshot of generated
`TOOL_SPECS` JSON; test fails on any accidental schema drift (pairs with H3).

**H12 · Deterministic session digest** (~half day): extends `_cad_state_blob`
with a tool-receipt timeline — the offline-first replacement for LLM
summarization of older turns; feeds long-session prompts at zero tokens.

**H13 · Judge best-of-3** (~half day): on a FAIL verdict, re-sample twice,
take 2-of-3 majority; records samples + extra tokens. Advisory policy unchanged.

**H14 · Router↔LLM handoff contract tests** (~half day): pin the "heuristics
assist only when LLM omits tools on first visit" semantics, so refactors can't
silently change who plans.

## Verification gates

- **Every push:** CI = full pytest (incl. browser) + key-less eval, on the branch.
- **Wave ends:** local full pytest + key-less eval; H3 and H7 waves additionally
  re-run the judge locally (`EVAL_JUDGE=1`) since they change behavior.
- **Before requesting merge:** judge-enabled eval run + a manual demo pass of
  the 22 catalog prompts (or the subset around changed paths).

## Risks

| Risk | Mitigation |
| :--- | :--- |
| H3 rejections break demo flows | Only affects args that bypassed the guardrail gap; catalog prompts already use in-range values or `update_design_program`; eval suite asserts the new rejections |
| H1/H7 shift agent answers | Judge rubrics grade quality not numbers; substring expectations flipped to tool-derived values; full eval re-run at wave end |
| H4 refactor regresses multi-turn memory | Browser multi-turn journeys + session consistency tests gate it |
| Token metering varies by provider | Fake-provider tests pin the contract; missing usage degrades to `null` |

## Explicitly out of scope

Response caching · LLM turn summarization · CI artifacts for eval history ·
new CAD parts/solvers · replacing the heuristic router with an LLM router.

## Interview payoff (one line per wave)

- **P0:** "I found three sources of truth for one concept and collapsed them to one — and my evals caught the gap that motivated it."
- **P1:** "The offline fallback is a designed, tested module — not 340 lines of keywords living in my agent's brain."
- **P2:** "Everything my agent emits — schemas, eval verdicts, session state — is pinned by contract tests."
