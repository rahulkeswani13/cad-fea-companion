# ADR-017: React console clarity — honest result labeling, session semantics, customer journeys

Date: 2026-09-06 · Status: accepted (recorded in PR 1 of 4; extended by each PR)

## Context

The React console (ADR-015) demos well to engineers but obfuscates three
things an interviewer or customer will probe: *how was this number produced*
(fallback results carry `fallback: true` on the wire but the UI never showed
it, so an analytical estimate could read as a live solve), *did the design
pass* (report cards and run rows stamped blanket PASS/FAIL verdicts,
conflating "the tool ran" with "the design is safe"), and *what did the agent
just do* (rails were populated from global disk state — design program and
run history — so a fresh session on a demo machine showed stale records as
if they belonged to the conversation). Library selection also auto-sent
prompts, walkthroughs were internal architecture tours (F02, F03, …), and
numeric formatting coerced missing values to zero (`Number(null) === 0`).

Constraints: AGENTS.md additive-first (no tool contract or wire-format
changes); the 45-check legacy browser suite stays green; offline-safe build
(no CDNs); every feature ships with tests + evals + talking-script + ADR.

This ADR records the decisions; the work lands in four PRs, each extending
this file:

1. `codex/console-honesty-pass` — result presentation (this revision).
2. `codex/console-demo-flow` — prompts, journeys, starters.
3. `codex/console-session-semantics` — session semantics.
4. `codex/console-cleanup` — cleanup and documentation.

## Decisions — PR 1: accurate result presentation

1. **Origin labels are read only from wire evidence** (`method`,
   `fallback`), never invented. Precedence:
   - explicit analytical method (`analytical_*`) → **Analytical estimate**,
     `ESTIMATE` stamp;
   - explicit saved/precomputed source (`*precomputed*`, `*saved*`) →
     **Saved reference result**, `REFERENCE` stamp;
   - `fallback: true` with unclear origin → **Fallback result**,
     `FALLBACK` stamp;
   - CalculiX method without fallback → **Live simulation**, no stamp.
   A fallback flag always overrides a live-sounding label (the fallback
   branch precedes the CalculiX branch), and fallback is never equated with
   analytical. Unknown method strings render verbatim. Results with no
   origin evidence get no label.
2. **Report-card stamps are execution outcomes only**: `Completed`
   (neutral) / `Failed` (red). The PASS/CAUTION/FAIL verdict stamp is
   removed from report cards *and* run-history rows; the numerical
   **safety factor versus yield** carries the verdict via the existing
   threshold colors (fail < 1, caution < 1.5, pass ≥ 1.5). `diverged`
   stays as a factual flag.
3. **Numeric honesty**: missing/empty/nonfinite values render as `—`
   (never zero); legitimate zeros pass through; presence-gated KPI rows
   cover all displacement variants (`pad_deflection_mm`,
   `tip_deflection_mm`, `deflection_mm`). `fmtNum` no longer coerces
   `null` to `0`.
4. **Friendly tool names**: the 13 registered tools map to plain-language
   names (e.g. `apply_load_and_solve` → "FEA solve"); unmapped tools fall
   back to a prettified raw name. Raw names remain visible in Technical
   details.
5. **Sources stay visible** as a compact per-message line (corpus paths);
   **Technical details** (collapsed per message) holds raw tool payloads
   verbatim, retrieval scores, rankings, and excerpts. Engineering
   limitations (NOT VERIFIED caveats) stay on the card.
6. **Eval delta: none** — presentation-only change; behavior is covered by
   browser tests (below) and no eval case semantics changed. Stated
   explicitly per the solver-honesty rule.

### PR 1 verification

- New browser tests (`tests/test_browser_ui.py` PART 4) intercept
  `/api/chat/stream` and `/api/runs` with deterministic fixtures:
  method-label precedence (five cases incl. fallback-over-live), execution
  status vs verdict, missing values/zeros, threshold-colored SF in history,
  sources/technical-details visibility, friendly vs raw names.
- Mocked browser tests establish UI behavior only — they are not AI or
  solver correctness evidence. Clearer fallback labels do **not** validate
  saved results against changed geometry (documented again in PR 4).

## Decisions — PR 2: prompts, journeys, starters

*(recorded when PR 2 merges)*

## Decisions — PR 3: session semantics

*(recorded when PR 3 merges)*

## Decisions — PR 4: cleanup and documentation

*(recorded when PR 4 merges)*

## Consequences

- Frontend-only so far; no endpoint, schema, `.env`, or packaging change.
- The origin-label precedence is a frontend reading of existing fields;
  backend provenance gaps (if any) remain unfixed by design — this is a
  presentation honesty pass, not a provenance rework.
- `web/` changes require `npm run build` before merge (committed build
  output); the legacy page is untouched and its 45 checks stay green.
