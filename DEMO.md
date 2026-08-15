# CAD/FEA Companion guide

This file covers how the project works and how to use every major path: chat UI, LangGraph agent, RAG, CAD/FEA tools, configuration, HTTP APIs, and tests.

## What it does

The companion is a **browser chat app** that:

1. Retrieves grounding snippets from local markdown in `docs/` (TF-IDF RAG).
2. Plans and calls **FreeCAD tools** (create geometry, mesh, solve, compare variants).
3. Keeps **thread memory** so follow-ups can reuse CAD state and prior results.
4. Streams status while tools run, and can pause for confirmation before mutating FreeCAD (HITL).

Chat is not inside FreeCAD. FreeCADCmd builds geometry and runs coarse Gmsh + CalculiX FEA; the GUI can open the latest `.FCStd` when requested.

Three geometry families:

| Part | Role | Web / variants | Default load |
|------|------|----------------|--------------|
| Brake pedal | Primary lattice bracket (pivot + clevis + footpad) | `solid` \| `xtruss` \| `fcc` | +500 N on the footpad (+X) |
| Engine mount | L-bracket (solid flange + pad, lattice web) | `solid` \| `bcc` \| `fcc` | 20 kN on the pad |
| Cantilever | Rectangular beam (regression / analytical check) | solid beam | 100 N tip load |

Material for the lattice parts is aluminum 6061-T6 (approx. E = 69 GPa, ν = 0.33, yield ~276 MPa). Compare tools recommend the **lightest variant with safety factor ≥ 1.5**.

## Start

```bash
cp .env.example .env          # set GEMINI_API_KEY for full LLM chat
./scripts/run_demo.sh
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Status pills show whether FreeCAD was found and whether Gemini is configured. **HITL** is off by default (`AGENT_REQUIRE_TOOL_CONFIRM=false`), so create/solve run without a confirm prompt.

Without `GEMINI_API_KEY`, the UI still runs: RAG plus heuristic one-tool-at-a-time routing. Add the key for full natural-language planning.

## Chat UI

- One **thread** per browser session (`thread_id`). Follow-ups reuse CAD geometry, FEA results, and chat history.
- Assistant replies can include **citations** (RAG), a **tool trace**, and streaming status (retrieve → plan → run tools → answer).
- If HITL is on, mutating FreeCAD tools pause until you confirm or cancel in the UI.

Useful first prompts are listed below; you can also call tools directly via `/api/tools/call`.

## How the agent works

Compiled graph in `companion/agent/graph.py`: **retrieve → agent ⇄ tools**, with CAD state sync, checkpointed by LangGraph `MemorySaver` on `thread_id`. Cap is `AGENT_MAX_TOOL_ROUNDS` (default 6).

```
  user message
       │
       ▼
  ┌─────────┐     citations from docs/ (TF-IDF)
  │ retrieve │     if cad_* empty, seed from the in-process FreeCAD session
  └────┬────┘
       ▼
  ┌─────────┐     tool calls          ┌──────────────┐
  │  agent  │────────────────────────►│    tools     │──► FreeCAD / metrics
  └────┬────┘◄────────────────────────│ sync_cad_…   │
       │         observations         └──────────────┘
       │ no more tools (or max rounds)
       ▼
      END  (+ MemorySaver checkpoint for the next turn)
```

| Idea | What it means here |
|------|--------------------|
| Tool loop | Call a tool, observe the result, then maybe call another (create, then solve). |
| Memory | Same `thread_id` remembers earlier turns (follow-up SF / mass questions). |
| CAD in graph state | Geometry and results live on the graph (`cad_geometry`, `cad_results`) and are seeded from the FreeCAD session if the checkpoint is empty. |
| HITL | Optional `interrupt()` before FreeCAD-mutating tools when `AGENT_REQUIRE_TOOL_CONFIRM=true`. |
| Streaming | `POST /api/chat/stream` narrates retrieve / tools / answer as SSE. |

On retrieve, if graph CAD fields are empty, the node copies them from `get_state()` so the agent knows about geometry already built in this server process.

## RAG

Corpus is the markdown under `docs/`, ingested into a local TF-IDF store at startup (`companion/rag/store.py`). No embedding API is required.

Typical grounding questions:

- *What yield strength should I assume for aluminum 6061-T6?* → ~240–276 MPa, with citations.
- *What relative density ranges are typical for lattice fills?*
- *What Young's modulus should I assume for 6061-T6?* → ~69 GPa.
- Units: stress in **MPa**, force in **N**, lengths in **mm**.

Re-ingest after editing docs: `POST /api/rag/ingest`. Search: `GET /api/rag/search?q=...`.

The agent is instructed to stay grounded: if the corpus does not support a claim (for example an unknown alloy), it should say so rather than invent numbers.

## Tools

| Tool | What it does |
|------|----------------|
| `create_brake_pedal` | Al pedal: solid rings + footpad; web `solid` \| `xtruss` \| `fcc`. Optional `cell_size_mm`, `strut_radius_mm`, `open_gui`. |
| `create_engine_mount` | L-bracket: solid flange + pad; web `solid` \| `bcc` \| `fcc`. |
| `create_cantilever` | Rectangular beam (`length_mm`, `width_mm`, `height_mm`). |
| `apply_load_and_solve` | Mesh (Gmsh) + solve (CalculiX). Defaults: 500 N / 5 mm pedal, 20 kN / 4 mm mount, 100 N / 2.5 mm cantilever. |
| `get_lattice_metrics` | Relative density, volumes, mass for the current pedal or mount. |
| `compare_brake_pedal_variants` | Solid vs X-truss vs FCC; lightest with SF ≥ 1.5. |
| `compare_mount_variants` | Solid vs BCC vs FCC; same SF rule. |
| `get_max_von_mises` | Latest max von Mises (MPa) and related KPIs. |
| `open_in_freecad` | Launch the GUI on the latest document. |

HITL applies to create / solve / open (`FREECAD_MUTATING_TOOLS`). Metrics and compare tools do not.

KPIs from a solve: mass, max von Mises, pad/tip deflection, safety factor vs yield. Default meshes are **coarse** so local solves stay practical. If CalculiX is unavailable, `FEM_ALLOW_ANALYTICAL_FALLBACK=true` can fall back to estimates or precomputed JSON (FCC KPIs are often precomputed by design).

## Walkthrough: brake pedal (primary)

1. **Grounding** — *What yield strength should I assume for aluminum 6061-T6?* Show citations.
2. **Solid baseline** — *Create a solid aluminum brake pedal and solve the +500 N footpad load along +X.* Trace: `create_brake_pedal` (`web_type=solid`) → `apply_load_and_solve`. Note mass, max von Mises, pad deflection.
3. **X-truss web** — *Rebuild with a 2.5D X-truss lattice web, same envelope, then solve.* Solid rings and footpad stay solid; the arm pocket is the design space. Expect **lower mass** vs a stress/stiffness tradeoff.
4. **Compare** — *Compare solid, X-truss, and FCC — which is lightest with safety factor at least 1.5?* Expect `compare_brake_pedal_variants`. Recommendation uses SF ≥ 1.5 vs ~276 MPa yield.

Design vs non-design on the pedal: pivot ring, clevis ring, footpad, and outer rim stay solid; only the inner arm pocket is lattice-filled. Details: `docs/brake_pedal_lattice.md`.

## Walkthrough: engine mount

- *Create a BCC engine mount lattice bracket and solve the pad load.* → `create_engine_mount` (`web_type=bcc`) → `apply_load_and_solve` (20 kN default).
- *Compare solid, BCC, and FCC engine mounts — lightest with SF at least 1.5.* → `compare_mount_variants`.

Flange and load pad are non-design (always solid); the web pocket is the design space. Details: `docs/engine_mount_lattice.md`.

## Walkthrough: cantilever

- *Create a cantilever 100×20×5 mm and apply 100 N tip load and solve.* → `create_cantilever` → `apply_load_and_solve`.
- Useful as a check against the analytical bending-stress formula in `docs/freecad_fem_notes.md`.

## Configuration

From `.env` (see `.env.example`):

| Variable | Role |
|----------|------|
| `GEMINI_API_KEY` | Required for full LLM chat |
| `GEMINI_MODEL` | Default `gemini-3.5-flash` |
| `FREECAD_CMD` | Override if `FreeCADCmd` is not on `PATH` |
| `HOST` / `PORT` | Server bind (default `127.0.0.1:8000`) |
| `ALLOW_REMOTE` | If false (default), reject non-localhost HTTP clients |
| `FEM_ALLOW_ANALYTICAL_FALLBACK` | Fall back when live CalculiX is unavailable |
| `AGENT_MAX_TOOL_ROUNDS` | Max agent ⇄ tools iterations (default 6) |
| `AGENT_REQUIRE_TOOL_CONFIRM` | HITL before FreeCAD-mutating tools |

## HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | Chat UI |
| `GET` | `/api/health` | FreeCAD path, LLM status, CAD state, HITL flags |
| `POST` | `/api/chat` | Invoke agent (`message`, `thread_id`, optional `resume` for HITL) |
| `POST` | `/api/chat/stream` | Same, Server-Sent Events |
| `GET` | `/api/tools` | Tool specs |
| `POST` | `/api/tools/call` | Call a tool directly (`name`, `args`) |
| `POST` | `/api/rag/ingest` | Rebuild the TF-IDF store from `docs/` |
| `GET` | `/api/rag/search` | Retrieve snippets (`q`, `k`) |
| `POST` | `/api/results/load_precomputed` | Load saved FEA JSON (`case=...`) |

## Precomputed results

If live meshing or solving is flaky, load saved KPIs and keep chatting about mass / stress / deflection:

```bash
curl -X POST "http://127.0.0.1:8000/api/results/load_precomputed?case=brake_xtruss"
```

| `case` | File |
|--------|------|
| `brake_xtruss` (and `brake_bcc` alias) | `data/results/brake_pedal_xtruss_precomputed.json` |
| `brake_solid` | `data/results/brake_pedal_solid_precomputed.json` |
| `brake_fcc` | `data/results/brake_pedal_fcc_precomputed.json` |
| `solid` / `bcc` / `fcc` | engine-mount JSON under `data/results/` |
| `cantilever` | `data/results/cantilever_precomputed.json` |

## Tests and eval

Mocked LangGraph tests (no FreeCAD, no live LLM):

```bash
.venv/bin/python -m pytest tests/ -q
```

Coverage includes the tool loop, thread memory, HITL interrupt/resume, and streaming.

Live / heuristic eval (RAG + tools + agent cases in `eval/cases.json`):

```bash
.venv/bin/python eval/run_eval.py
```

FreeCAD geometry smoke (create cantilever, pedal, mount; no full solve required):

```bash
.venv/bin/python scripts/smoke_freecad.py
```

## Layout

- `companion/agent/` — LangGraph graph, tool schemas, HITL
- `companion/tools/` — FreeCAD runtime, brake pedal, engine mount, cantilever, solve
- `companion/rag/` — local TF-IDF ingest and retrieve
- `companion/llm/` — Gemini provider
- `companion/static/index.html` — chat UI
- `docs/` — RAG corpus
- `eval/` — cases + runner
- `tests/` — proving suite
- `data/results/` — precomputed FEA JSON
- `data/workspace/` — generated `.FCStd` / exports (gitignored)
