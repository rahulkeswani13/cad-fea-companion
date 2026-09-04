"""FastAPI app: chat UI + CAD/FEA companion API."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from companion.agent.confirm import (
    get_require_tool_confirm,
    require_tool_confirm_source,
    set_require_tool_confirm,
)
from companion.agent.graph import run_agent, session_usage, stream_agent
from companion.config import get_settings
from companion.llm.providers import provider_status
from companion.rag.store import get_store, ingest_docs, retrieve_detail
from companion.tools.cad_fea import (
    TOOL_SPECS,
    call_tool,
    get_design_program,
    get_state,
    load_precomputed_results,
)
from companion.tools.freecad_runtime import find_freecad_cmd
from companion.tools.outcome import wrap_tool_call
from companion.tools.run_history import read_runs

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="CAD/FEA Chat Companion", version="0.2.0")

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def client_is_loopback(host: str | None) -> bool:
    if not host:
        return False
    h = host.strip().lower()
    if h.startswith("::ffff:"):
        h = h[7:]
    return h in _LOOPBACK_HOSTS


@app.middleware("http")
async def local_only(request: Request, call_next):
    settings = get_settings()
    if not settings.allow_remote and not client_is_loopback(
        request.client.host if request.client else None
    ):
        return JSONResponse(
            {
                "error": (
                    "This server only accepts local connections. "
                    "Set ALLOW_REMOTE=true in .env to override."
                )
            },
            status_code=403,
        )
    return await call_next(request)


class ChatRequest(BaseModel):
    message: str = Field(default="", min_length=0)
    thread_id: str | None = None
    resume: bool | dict[str, Any] | None = None


class ToolRequest(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


@app.on_event("startup")
def startup() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    ingest_docs()


@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "ok": True,
        "freecad_cmd": find_freecad_cmd(),
        "llm": provider_status(settings),
        "state": get_state(),
        "agent": {
            "max_tool_rounds": settings.agent_max_tool_rounds,
            "require_tool_confirm": get_require_tool_confirm(),
        },
        "session_usage": session_usage(),
    }


def _chat_error(exc: Exception, thread_id: str | None = None) -> dict[str, Any]:
    return {
        "answer": "",
        "citations": [],
        "grounding": "none",
        "tool_calls": [],
        "tool_results": [],
        "error": str(exc),
        "llm_configured": get_settings().llm_configured(),
        "thread_id": thread_id,
        "interrupted": False,
        "interrupt": None,
    }


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    tid = req.thread_id or str(uuid.uuid4())
    try:
        if req.resume is not None:
            return run_agent(thread_id=tid, resume=req.resume)
        if not req.message.strip():
            return {
                **_chat_error(ValueError("message is required unless resume is set"), tid),
                "error": "message is required unless resume is set",
            }
        return run_agent(req.message, thread_id=tid)
    except Exception as exc:  # noqa: BLE001 — surface LLM/tool failures as JSON
        return _chat_error(exc, tid)


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    tid = req.thread_id or str(uuid.uuid4())

    def event_gen():
        try:
            if req.resume is not None:
                events = stream_agent(message="", thread_id=tid, resume=req.resume)
            elif not req.message.strip():
                yield f"data: {json.dumps({'type': 'final', 'error': 'message required', 'thread_id': tid})}\n\n"
                return
            else:
                events = stream_agent(req.message, thread_id=tid)
            for event in events:
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'final', 'error': str(exc), 'thread_id': tid})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/api/tools")
def list_tools() -> dict[str, Any]:
    return {"tools": TOOL_SPECS}


@app.post("/api/tools/call")
def tools_call(req: ToolRequest) -> dict[str, Any]:
    return call_tool(req.name, req.args)


@app.post("/api/rag/ingest")
def rag_ingest() -> dict[str, Any]:
    return ingest_docs()


@app.get("/api/rag/search")
def rag_search(q: str, k: int = 4, detail: int = 0) -> dict[str, Any]:
    if detail:
        breakdown = retrieve_detail(q, k=k)
        return {"query": q, **breakdown}
    return {"query": q, "hits": retrieve_detail(q, k=k)["fused"]}


@app.get("/api/rag/stats")
def rag_stats() -> dict[str, Any]:
    return get_store().stats()


@app.post("/api/results/load_precomputed")
def results_load(case: str = "auto") -> dict[str, Any]:
    return wrap_tool_call(
        "load_precomputed_results",
        {"case": case},
        lambda name, args: load_precomputed_results(
            case=str(args.get("case") or "auto")
        ),
        state_fn=get_state,
    )


RUN_ROW_KEYS = (
    "run_id",
    "part",
    "web_type",
    "force_n",
    "method",
    "max_von_mises_mpa",
    "max_vm_location_mm",
    "safety_factor_vs_yield",
    "mesh_max_size_mm",
    "divergence_flag",
    "ts",
)

PROMPTS_PATH = Path(__file__).resolve().parents[1] / "data" / "prompts.json"


def _load_prompts() -> dict[str, Any]:
    """Console prompt library (ADR-015); data/prompts.json is the source of truth."""
    return json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))


def _active_part_from_state() -> str | None:
    geometry = get_state().get("geometry") or {}
    part = str(geometry.get("part") or "").strip()
    return part or None


def _program_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Compact read-only view of get_design_program for the state rail."""
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error"),
            "correction": result.get("correction"),
            "note": result.get("note"),
            "programs": result.get("programs"),
        }
    params = result.get("params") or {}
    payload: dict[str, Any] = {
        "ok": True,
        "part": result.get("part"),
        "rev": result.get("rev"),
        "params_hash": result.get("params_hash"),
        "params": [
            {"key": key, "value": params[key]} for key in sorted(params)
        ],
        "active_part": _active_part_from_state(),
    }
    if result.get("programs") is not None:
        payload["programs"] = result["programs"]
    if result.get("note") is not None:
        payload["note"] = result["note"]
    return payload


def _run_row(run: dict[str, Any]) -> dict[str, Any]:
    return {key: run.get(key) for key in RUN_ROW_KEYS if run.get(key) is not None}


def _run_rows(part: str | None, limit: int) -> dict[str, Any]:
    """Compact read-only view of run history for the state rail (F06)."""
    limit = max(1, min(50, int(limit)))
    settings = get_settings()
    part = (part or "").strip() or _active_part_from_state()
    if not part:
        candidates = sorted(
            settings.workspace_dir.glob("*_runs.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return {"part": None, "runs": []}
        part = candidates[0].name.removesuffix("_runs.jsonl")
    rows = [_run_row(run) for run in read_runs(part, last_n=50)]
    rows = [row for row in rows if row]
    rows.sort(key=lambda row: str(row.get("ts") or ""), reverse=True)
    return {"part": part, "runs": rows[:limit]}


_CONSOLE_PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>CAD/FEA Companion — Console</title>
<style>body{background:#12140f;color:#e9ebe2;font:14px monospace;display:grid;
place-items:center;min-height:100vh;margin:0}div{max-width:42ch;padding:2rem;
border:1px solid #2e332a;border-radius:4px}code{color:#ff5c1f}</style></head>
<body><div><strong>Console build missing.</strong><br><br>
The React console is built from <code>web/</code> into
<code>companion/static/app/</code> — run <code>npm run build</code> there
(see ADR-015). The legacy console at <a href="/" style="color:#ff5c1f">/</a>
still works.</div></body></html>"""


@app.get("/app")
def console() -> Any:
    built = STATIC_DIR / "app" / "index.html"
    if built.exists():
        return FileResponse(built)
    return HTMLResponse(_CONSOLE_PLACEHOLDER)


@app.get("/api/prompts")
def prompts() -> Any:
    try:
        return _load_prompts()
    except FileNotFoundError:
        return JSONResponse(
            {
                "error": f"prompt library missing at {PROMPTS_PATH.name}",
                "correction": "restore data/prompts.json from version control (ADR-015).",
            },
            status_code=500,
        )
    except json.JSONDecodeError as exc:
        return JSONResponse(
            {
                "error": f"prompt library is not valid JSON: {exc.msg}",
                "correction": "fix data/prompts.json syntax and reload (ADR-015).",
            },
            status_code=500,
        )
    except Exception:  # noqa: BLE001 — compact failure, never a raw traceback
        return JSONResponse(
            {
                "error": "prompt library could not be loaded",
                "correction": "check server logs for the loader failure (ADR-015).",
            },
            status_code=500,
        )


@app.get("/api/design-program")
def design_program(part: str | None = None) -> dict[str, Any]:
    return _program_payload(get_design_program(part))


@app.get("/api/runs")
def runs(part: str | None = None, limit: int = 10) -> dict[str, Any]:
    return _run_rows(part, limit)


@app.get("/api/solver-status")
def solver_status() -> dict[str, Any]:
    settings = get_settings()
    freecad_cmd = find_freecad_cmd()
    return {
        "freecad": bool(freecad_cmd),
        "freecad_cmd": freecad_cmd,
        "llm": provider_status(settings),
        "require_tool_confirm": get_require_tool_confirm(),
        "confirm_source": require_tool_confirm_source(),
    }


class ToolConfirmRequest(BaseModel):
    enabled: bool


@app.post("/api/tool-confirm")
def tool_confirm(req: ToolConfirmRequest) -> dict[str, Any]:
    """Runtime HITL toggle (ADR-016): the operator decides per session whether
    FreeCAD-mutating tools pause for confirmation. Effective immediately."""
    enabled = set_require_tool_confirm(req.enabled)
    return {
        "require_tool_confirm": enabled,
        "confirm_source": require_tool_confirm_source(),
    }


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "companion.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
