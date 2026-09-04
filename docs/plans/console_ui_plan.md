# Console UI plan — React console at `/app` (F27, ADR-015)

Goal: a demo-first, still-daily-usable console for the CAD/FEA Companion —
beautiful enough to headline an interview, real enough to drive parts with.
Ships additively: the legacy console (`/` + `/static/*`) stays untouched and
the 45 existing browser checks stay green.

## Settled decisions (grilled 2026-09-02)

| Decision | Choice |
| :--- | :--- |
| Purpose | Demo-first showpiece that stays a working console |
| Stack | Vite + React + TypeScript + Tailwind v4, no component library |
| Delivery | Build output committed to `companion/static/app/`, served at `/app`; legacy page untouched |
| Prompt source of truth | `data/prompts.json` served via new `GET /api/prompts` |
| Prompt picker | Categorized dropdown on the composer + ⌘K searchable palette sharing one data source |
| Session model | Single active thread + "New session" (v1) |
| Walkthrough mode | In v1 — Features.md scripted prompts as guided steps with talking points |
| Aesthetic | **"Test Report"** — industrial/technical direction (ADR-015 §Design) |

## Design direction — "Test Report" (anti-slop committed)

The UI looks like an engineering test report because the product *is* one:
receipts, design programs, mesh sizes, solver honesty. Chosen over the
"dark dashboard + glow" default (Linear-glow / navy-SaaS tells) and over
editorial/Swiss options.

1. **Type:** Archivo Variable (display, expanded widths) + IBM Plex Sans
   (body) + IBM Plex Mono (all data/readouts). Self-hosted via `@fontsource`
   so the demo works offline. No Inter, no Space Grotesk, no Geist.
2. **Palette (60/30/10):** warm graphite base `#12140f` (green-tinted
   near-black, not navy), off-white ink `#e9ebe2`, hairlines `#2e332a`;
   **one brand accent: signal orange `#ff5c1f`** for interactive emphasis
   only; green/amber/red appear *only* as semantic solver states
   (pass / caution / fail). Zero gradients, zero glows; borders over
   shadows; radius 2–4 px, sharp on data surfaces.
3. **Layout:** three-zone console — left rail (01 Feature Walkthroughs,
   02 Prompt Library), center chat stream + composer, right rail
   (03 Design Program, 04 Run History, 05 Solver Status). Rails collapse;
   flush-left, visible hairline rules, numbered sections as a deliberate
   spec-sheet system.
4. **Motion:** near-none; one signature entrance — tool receipts *stamp*
   into the log (150 ms ease-out, no bounce); streaming status line updates
   in place.
5. **Signature detail:** every FEA tool result renders as a **report card** —
   tool name, ok/failed stamp, KPI rows (σ, SF, mass, δ, ρ\*), method
   (calculix/surrogate/analytical), mesh size, divergence flag, and
   `NOT VERIFIED` caveats — making the solver-honesty pattern visible.

De-slop guardrails baked into implementation review: no purple/indigo, no
gradient headline text, no glassmorphism, no colored left-border stripes,
no emoji icons (custom 1.5 px inline SVG marks only), no reflexive all-caps
eyebrows (numbered index system instead), real hover/focus/disabled states
everywhere, meaningful contrast (AA+).

## Architecture

```
web/                          # Vite project (npm run build → ../companion/static/app)
  src/
    lib/                      # api client, SSE reader, markdown pipeline, format, icons
    components/               # TopBar, RailLeft, RailRight, ChatStream, Message,
                             # ReportCard, Composer, PromptMenu, CommandPalette,
                             # Walkthrough, DesignProgramCard, RunHistoryCard,
                             # SolverStatusCard, primitives/
companion/static/app/         # committed build output (gitignored? no — committed)
companion/main.py             # + GET /app, /api/prompts, /api/design-program,
                              #   /api/runs, /api/solver-status  (all additive)
data/prompts.json             # prompt library + walkthrough scripts (source of truth)
```

Chat protocol reuses the existing wire format exactly (SSE `node`/`final`
events, `resume` flow, HITL confirm bar) — the new console is a second
client, not a new contract.

## Backend additions (all additive)

- `GET /app` — serves the built console; falls back to a "run
  `npm run build`" placeholder if the build is missing.
- `GET /api/prompts` — reads `data/prompts.json`; 404-shaped compact error
  if the file is malformed (fail closed with one correction).
- `GET /api/design-program` — thin read over `get_design_program()`
  (active part or `?part=`).
- `GET /api/runs` — thin read over `run_history.read_runs` for the active
  part (or `?part=`), latest first, capped rows.
- `GET /api/solver-status` — FreeCAD availability + LLM provider status +
  HITL flag (compact; `/api/health` stays as-is).

## Prompt library content

`data/prompts.json` carries two collections:
- `categories`: prompt items grouped (Grounded Q&A, CAD Builds, FEA Solves,
  Variants & Trade-offs, Diagnostics & History), each item with
  `id/title/prompt`, `freecad` flag (will launch FreeCAD work) and `cost`
  hint (instant / seconds / solve).
- `features`: one entry per Features.md feature (F02–F14) with `steps` —
  ordered prompts + `talking_points` — powering walkthrough mode.

## Verification plan

- Unit tests `tests/test_console_api.py`: every new endpoint (contract,
  compact shapes, fallbacks, `/app` placeholder when build absent).
- Browser checks `tests/test_browser_ui.py` (new section, same mocked-LLM
  fixture): console loads at `/app`, prompt dropdown lists library items,
  ⌘K palette opens and inserts a prompt, walkthrough step sends, report
  card renders on a tool result.
- Eval cases: new `http` case type in `eval/run_eval.py` (additive elif)
  hitting the real app via TestClient — prompts contract, design-program
  shape, runs shape, solver-status shape.
- Docs: ADR-015, this plan, Features.md `F27` talking-script section +
  reconciled inventory counts, README quickstart note.

## Ship order (PR-sized chunks)

1. Scaffold + tokens + shell + `/app` route (console renders, legacy green).
2. Chat parity + report cards + prompt dropdown/palette (`/api/prompts`).
3. State rail endpoints + walkthrough mode + docs/evals wrap-up.

Implemented as one working-tree change set here; split along the seams
above when committing/PR-ing.
