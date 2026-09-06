# web/ — React console (served by FastAPI at `/app`)

Build-time only: the Python runtime never needs node. Build output is
committed to `companion/static/app/` and served additively next to the
legacy console (`/`), which stays untouched (ADR-015).

```bash
cd web
npm install        # once
npm run build      # type-checks, then bundles into ../companion/static/app
npm run dev        # optional: Vite dev server on :5173, /api proxied to :8000
```

After changing anything under `src/`, run `npm run build` before merging so
the committed bundle matches the source.

## Demo contract (ADR-017)

- **Selection never executes.** Sidebar, ⌘K palette (Enter included),
  composer dropdown, journeys, and welcome starters all *fill the composer*;
  only **Send** runs.
- **Guided journeys** live in `src/lib/journeys.ts` and reference canonical
  library prompt ids from `data/prompts.json` — the executable text stays
  single-sourced (ADR-015). Conversational steps may carry inline text.
  Journeys advance manually; the UI never claims a step completed.
- **Session semantics**: every page load starts a fresh conversation (the
  stored thread id is never restored; server checkpoints on disk are
  untouched). The right rail shows *Runs in this session* — observed solves
  only, `run_id`-deduplicated, convergence sub-runs included, failed mesh
  attempts visible — with the persisted audit trail under the collapsed
  *Recent saved runs* disclosure. The design panel is the *Saved workspace
  design* and may belong to another session. New session is disabled while
  busy; in-flight responses from an obsolete session generation are dropped.
- **Result honesty**: origin labels read only wire evidence
  (`method`, `fallback`) with strict precedence — Live simulation /
  Analytical estimate / Saved reference result / Fallback result; the card
  stamp is the execution outcome (Completed/Failed); the safety-factor
  number carries the verdict via threshold colors; missing values render as
  `—`, never zero. Raw payloads and retrieval diagnostics collapse under
  *Technical details*.
- Caveat: clearer labels do not re-validate saved/fallback results against
  changed geometry — check the design-program revision before trusting a
  saved result.

Design system: see `docs/plans/console_ui_plan.md` and ADR-015 ("Test
Report" direction — tokens live in `src/styles.css`); clarity decisions in
`docs/adr/ADR-017-react-console-clarity.md`.
