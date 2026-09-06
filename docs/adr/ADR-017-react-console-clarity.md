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

1. **Task-oriented library groups** in `data/prompts.json` (version 1.1):
   Create a part / Run analysis / Compare options / Edit a design /
   Inspect results / Engineering help, plus **Try validation errors**
   (collapsed by default in the UI) holding `diag-guardrail` and two new
   validation prompts (`err-solve-empty` — no-geometry solve, `err-unknown-material`
   — unknown material). Existing item ids are preserved; four items added
   (`solve-cantilever`, `qa-material-guidance`, the two validation
   prompts). Operation coverage is unchanged.
2. **Selection never executes**: every entry point — sidebar, ⌘K palette
   (Enter included), composer dropdown, journeys, starters — fills the
   composer for inspection and editing; only **Send** runs. The palette's
   Enter-to-send shortcut is retired (demo safety: a wrong send costs a
   FreeCAD solve).
3. **Three guided journeys** replace the internal feature tours as the
   visible walkthroughs: UAV arm design iteration (5 steps), cantilever
   analysis checks (4), brake pedal material comparison (5). Journeys live
   in **frontend configuration** (`web/src/lib/journeys.ts`) and reference
   canonical library prompt ids; conversational steps may carry inline
   text. The prompt API and `features` wire shape are preserved untouched —
   the technical walkthroughs stay served in `features` and documented in
   `demo/Features.md`; the UI does not render them.
4. **Journey presentation**: purpose, prerequisites, explicit step position
   ("step k of n"), Previous/Next, **Use prompt** (fills). Navigation is
   manual — the console never claims a step completed.
5. **Four welcome starters** on the empty state, referencing library items:
   Create a UAV arm, Create a brake pedal, Create a cantilever beam,
   Ask about materials (→ `qa-material-guidance`). Fill-only.
6. **Eval**: `tool_reject_unknown_material` (create with an unknown
   material → `bad_params` + correction naming valid ids). The RAG-side
   refusal case already existed.

### PR 2 verification

- Browser tests: journey navigation + Use-prompt-fills; sidebar/palette/
  starters fill without sending (`msg-user` count stays 0); new group
  titles render; prompts shape/unique-id API tests unchanged and green.

## Decisions — PR 3: session semantics

1. **Fresh conversation on every full page load**: the stored thread id is
   never restored (the legacy `cad_fea_thread_id` key is removed on boot);
   the server thread id returned in responses is adopted in memory only.
   Theme and rail-width preferences still persist. Server-side thread
   checkpoints on disk are untouched.
2. **New session** clears chat, composer, interruptions, journey progress,
   and session runs; the top-bar button is **disabled while busy**.
3. **Leave warning while busy**: a `beforeunload` guard registers when a
   request is in flight; the console explains in its own UI that work may
   continue after leaving and never claims cancellation — the native
   dialog wording belongs to the browser.
4. **Obsolete-response guard**: each send/resume captures a frontend
   session generation; a response belonging to an older generation is
   dropped instead of landing in a newer conversation. The guard is
   defense-in-depth behind the disabled button (the function is kept
   callable for the race path; browser click suppression on disabled
   buttons is not relied on).
5. **Runs in this session**: the rail's run card lists only solve
   operations observed during this frontend session — arrival order,
   `run_id` deduplication (convergence replays the base run), convergence
   sub-runs included, failed mesh attempts shown as `failed`. Results
   returned by historical queries (`query_results`) never become session
   runs. A solve whose recording degraded (no `run_id`) still displays
   with an explicit **unrecorded** marker — no invented persisted identity.
6. **Saved workspace design**: the global design panel is renamed and
   carries a visible note that it may belong to another session — the
   design program on disk is the accepted source of truth (AGENTS.md),
   not the conversation's live state.
7. **Recent saved runs**: a collapsed disclosure over the existing
   `/api/runs` endpoint shows the selected part and the latest eight
   records — the persistence/audit-trail story stays reachable without
   polluting the session view.
8. **Eval delta: none** — frontend state and presentation only; no agent
   or tool semantics changed.

### PR 3 verification

- Browser tests: clean launch with disk history (session empty, disclosure
  populated), reset clearing everything, busy-state protection (button
  disabled, note visible) with a forced reset proving stale responses are
  ignored, missing-`run_id` unrecorded marker, convergence sub-run dedup
  with failed attempts.

## Decisions — PR 4: cleanup and documentation

1. **Numbered section prefixes (01–05) and visible feature ids are
   removed from the console UI**; headings are plain language
   (Saved workspace design / Runs in this session / Recent saved runs /
   Solver status / Guided journeys / Prompt library). Internal ids remain
   in data files and test selectors.
2. **TopBar keeps its thread/token display** (compact, demo-relevant);
   raw payloads and diagnostics live under Technical details per PR 1.
3. **Documentation**: `web/README.md` documents the demo contract
   (fill-only selection, journeys, session semantics, gates);
   `docs/PLAN.md` records the work as F31; `demo/Features.md` carries the
   talking-script sections (F31–F34) alongside the preserved technical
   feature walkthroughs.
4. **Explicit caveat, stated twice on purpose**: clearer fallback labels
   are presentation honesty only — they do **not** validate saved or
   fallback results against changed geometry. A Saved reference result
   replayed after parameters changed is still a saved result; check the
   design-program revision before trusting it.
5. **Classic console (`/`) and RAG Lab (`rag.html`) untouched**; verified
   they do not consume `/api/prompts` — the regrouped `data/prompts.json`
   categories affect the React console only.

## Status

Accepted and fully implemented across the four PRs (2026-09-06).

## Consequences

- Frontend-only so far; no endpoint, schema, `.env`, or packaging change.
- The origin-label precedence is a frontend reading of existing fields;
  backend provenance gaps (if any) remain unfixed by design — this is a
  presentation honesty pass, not a provenance rework.
- `web/` changes require `npm run build` before merge (committed build
  output); the legacy page is untouched and its 45 checks stay green.
