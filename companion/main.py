"""FastAPI app: chat UI + CAD/FEA companion API."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from companion.agent.graph import run_agent, stream_agent
from companion.config import get_settings
from companion.llm.providers import provider_status
from companion.rag.store import ingest_docs, retrieve
from companion.tools.cad_fea import (
    TOOL_SPECS,
    call_tool,
    get_state,
    load_precomputed_results,
)
from companion.tools.freecad_runtime import find_freecad_cmd

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
            "require_tool_confirm": settings.agent_require_tool_confirm,
        },
    }


def _chat_error(exc: Exception, thread_id: str | None = None) -> dict[str, Any]:
    return {
        "answer": "",
        "citations": [],
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
def rag_search(q: str, k: int = 4) -> dict[str, Any]:
    return {"query": q, "hits": retrieve(q, k=k)}


@app.post("/api/results/load_precomputed")
def results_load(case: str = "auto") -> dict[str, Any]:
    return load_precomputed_results(case=case)


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
