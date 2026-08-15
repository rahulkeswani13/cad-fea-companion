# CAD/FEA Chat Companion

A local **chat UI + RAG + tool-calling agent** that drives FreeCAD CAD and coarse static FEA.

Ask about materials and lattice design in natural language, then create geometry, solve a load case, and compare solid vs lattice variants — all from the browser. Chat lives in **your** UI; FreeCAD is the geometry and FEM backend.

Primary example: an aluminum **brake-pedal** bracket with a solid or lattice web (X-truss / FCC). The same agent also drives an **engine-mount** L-bracket and a **cantilever** beam.

See `DEMO.md` for a full walkthrough (agent loop, RAG, tools, HITL, streaming, APIs, tests).

## Architecture

```
Browser chat → FastAPI → LangGraph agent (retrieve → agent ⇄ tools)
                          ├─ MemorySaver thread memory
                          ├─ TF-IDF RAG over docs/
                          ├─ FreeCADCmd tools (pedal / mount / cantilever / solve)
                          └─ Gemini via .env
```

## Requirements

- Python 3.11+
- [FreeCAD](https://www.freecad.org/) with `FreeCADCmd` on your `PATH` (or set `FREECAD_CMD` in `.env`)
- A Gemini API key (`GEMINI_API_KEY`) for full chat; the UI still runs without one
- Bind stays on localhost by default (`ALLOW_REMOTE=true` required to accept non-local clients)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set GEMINI_API_KEY=...
```

Install FreeCAD if needed, then confirm the CLI is visible:

```bash
which FreeCADCmd || echo "Set FREECAD_CMD in .env to your FreeCADCmd path"
```

On macOS with Homebrew, `brew install --cask freecad` is one option.

## Run

```bash
chmod +x scripts/run_demo.sh
./scripts/run_demo.sh
```

Or:

```bash
source .venv/bin/activate
.venv/bin/python -m uvicorn companion.main:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Without an API key, RAG and heuristic tool routing still work. Full LLM answers activate after `.env` is filled.

## Example prompts

1. *What yield strength should I assume for aluminum 6061-T6?*
2. *Create a solid aluminum brake pedal and solve the +500 N footpad load along +X.*
3. *Rebuild with a 2.5D X-truss lattice web, same envelope, then solve.*
4. *Compare solid, X-truss, and FCC — which is lightest with safety factor at least 1.5?*

## Tests

```bash
.venv/bin/python -m pytest tests/ -q          # agent loop (mocked LLM/tools)
.venv/bin/python scripts/smoke_freecad.py     # live FreeCAD geometry
.venv/bin/python eval/run_eval.py             # RAG + tools + agent cases
```

## Precomputed results

If a live FreeCAD solve is unavailable, load saved KPIs:

```bash
curl -X POST "http://127.0.0.1:8000/api/results/load_precomputed?case=brake_xtruss"
```

Cases: `brake_xtruss`, `brake_solid`, `brake_fcc`, `bcc` / `solid` / `fcc` (engine mount), `cantilever`.

## Project layout

- `companion/` — FastAPI app, LangGraph agent, RAG, Gemini client, FreeCAD tools, chat UI
- `docs/` — RAG corpus (materials, lattice notes, FEM notes)
- `eval/` — RAG + tool + agent cases and runner
- `tests/` — LangGraph tests (loop, memory, HITL, stream)
- `scripts/run_demo.sh` — local start (venv, ingest, uvicorn)
- `.env.example` — Gemini and agent settings

## License

Local companion code for this repository. FreeCAD is separate software under its own license.
