# ADR-015: React console at `/app` (additive second client)

Date: 2026-09-02 · Status: accepted

## Context

The chat console (`companion/static/index.html`) is a single-file vanilla
page: one column, five hardcoded example prompts, a link out to the RAG Lab.
The demo story (14 scripted features in `demo/Features.md`) is richer than
the UI can express: there is no way to browse a prompt library, no live view
of the design program or run history, no guided walkthrough for a recorded
or live interview. "Beautiful" was an explicit goal, and the existing page
has hit the ceiling of hand-rolled single-file CSS.

Constraints that shaped the choice:

- AGENTS.md: additive-first; no contract changes without an ADR; every
  feature ships with tests + evals + talking-script + ADR.
- 45 Playwright browser checks run against the legacy page's selectors and
  must stay green through the migration.
- Demos happen offline and on projectors; the console must not depend on
  network CDNs at runtime.
- The repo is deliberately Python-only today; any frontend toolchain is a
  new permanent cost and needs justification.

## Decisions

1. **React + Vite + TypeScript + Tailwind, no component library.** A
   componentized UI pays for the toolchain: the console is panels, lists,
   tables, and overlays — component structure, not hand CSS, keeps it
   maintainable. Primitives are hand-rolled (no shadcn) because an untouched
   component-kit default is exactly the look we are avoiding, and the design
   needs few primitives.
2. **Additive second client at `/app`.** The build output is committed to
   `companion/static/app/` and served by FastAPI; the legacy page stays the
   default until the console is at parity. No existing endpoint, schema, or
   selector changes; the chat wire protocol (SSE `node`/`final`, resume
   flow) is reused as-is. Flipping the default is a later, separate change.
3. **One data source for prompts: `data/prompts.json` + `GET /api/prompts`.**
   Demo prompts are versioned data (id, title, prompt, FreeCAD/cost flags,
   walkthrough steps with talking points), not prose embedded in a component
   or scraped from Features.md at runtime. Seeded from Features.md; the doc
   stays the human talking script, the JSON stays the machine contract.
4. **Design direction: "Test Report" (industrial/technical).** Warm graphite
   + signal orange accent; Archivo / IBM Plex Sans / IBM Plex Mono
   self-hosted via @fontsource (offline-safe); hairline borders over
   shadows; green/amber/red reserved for solver semantics; FEA results
   rendered as stamped report cards surfacing method/mesh/caveats. Rejected:
   the "dark navy + glow" SaaS default (generic AI aesthetic) and light
   Swiss (weaker on a projector for this content).
5. **New read-only endpoints** (`/api/prompts`, `/api/design-program`,
   `/api/runs`, `/api/solver-status`) are thin additive GETs over existing
   Python state (`get_design_program`, `run_history`, `provider_status`,
   `find_freecad_cmd`). No tool schemas, `.env` keys, or defaults change.

## Consequences

- `web/` introduces node/npm as a build-time dependency. Runtime stays
  pure FastAPI + static files; CI stays zero-API-cost (Playwright suites
  run against committed build output; no npm in CI).
- Committed build output means UI changes require a rebuild before merge;
  `web/README.md` documents the two commands (`npm install`, `npm run build`).
- The legacy page and the console coexist until parity; removing the legacy
  page afterwards is a separate ADR.
