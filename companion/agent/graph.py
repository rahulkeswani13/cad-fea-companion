"""LangGraph agent: retrieve → agent ⇄ tools (with CAD state, memory, HITL)."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Iterator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt

from companion.agent.context import condense_history
from companion.agent.heuristics import HeuristicRouter
from companion.agent.tools import FREECAD_MUTATING_TOOLS, get_langchain_tools
from companion.config import Settings, get_settings
from companion.llm.providers import (
    AgentTurn,
    LLMNotConfiguredError,
    LLMProvider,
    ToolCallSpec,
    get_llm_provider,
)
from companion.rag.store import retrieve_detail
from companion.tools import materials as mats
from companion.tools import outcome
from companion.tools.cad_fea import TOOL_SPECS, cad_thread_scope, call_tool, get_state

CallToolFn = Callable[[str, dict[str, Any] | None], dict[str, Any]]


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    message: str
    citations: list[dict[str, Any]]
    grounding: str | None
    pending_tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    cad_geometry: dict[str, Any] | None
    cad_results: dict[str, Any] | None
    answer: str
    error: str
    iteration: int
    agent_visits: int
    tools_node_visits: int
    # H2: per-run token totals across this run's LLM calls (None = no LLM use).
    usage: dict[str, int] | None


SYSTEM_PROMPT = """You are a CAD/FEA engineering companion.
Primary example: aluminum brake-pedal lattice bracket (pivot + clevis rings + footpad) with a
lattice web (solid | xtruss | fcc). Also supported: cantilever beam.

Rules:
- Prefer grounded answers from retrieved context and tool results.
- If context is insufficient for a factual claim, say you do not know.
- When the user asks to create geometry or run FEA, use tools — usually one step at a time,
  then observe the tool result before the next tool.
- Prefer reusing existing geometry/results in session state; do not recreate unless asked.
- If a tool returns ok:false, decide the next action from that observation (retry, create first, etc.).
- create_brake_pedal / create_uav_arm / create_cantilever and apply_load_and_solve open
  FreeCAD GUI when available.
- For brake pedals: discuss design vs non-design regions (solid rings + footpad vs lattice pocket),
  relative density, mass, pad deflection, max von Mises vs Al 6061-T6 yield (~276 MPa), and SF.
  Default load is +500 N on the footpad opposite (-X) face (Fx=+500). Fixed on pivot ID and clevis ID.
  Prefer web_type=xtruss (2.5D diagonal X-truss); "bcc" aliases to xtruss on the pedal.
- Coarse CalculiX tet meshes under-predict peak stress (especially in struts). For the
  cantilever, mention analytical_reference_mpa (~120 MPa for 100 N / 100x20x5 mm).
- Use compare_brake_pedal_variants when the user asks
  which lattice is best / lightest under constraints.
- Use compare_materials for material trade-off questions ("Ti vs Al", "what
  about printed nylon"). It scales the best available run linear-elastically;
  state the method and quote the row sources. PA12 deflection is flagged
  NOT VERIFIED — say so. To actually change material, use update_design_program
  with a changes object setting "material" (rebuilds + bumps the program
  revision).
- Use run_convergence_study when the user asks whether results are mesh-converged
  or wants a mesh sensitivity check; it is synchronous (costs 2-3 solves) and its
  report states the recommended mesh size. Answers derived from it must state the
  mesh size used (solver honesty).
- Keep answers concise and cite sources as [source].

Session CAD state:
{cad_state}

Retrieved context:
{context}

Available tools (JSON):
{tools}
"""


def _parse_tool_plan(text: str) -> list[dict[str, Any]]:
    match = re.search(r"```tools\s*(\[.*?\])\s*```", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict) and "name" in x]
    except json.JSONDecodeError:
        return []
    return []


# H6: the offline-first planner is a designed module now; these wrappers keep
# the historical graph-module import surface working.
_ROUTER = HeuristicRouter()


def _pedal_oriented(message: str) -> bool:
    return _ROUTER.pedal_oriented(message)


def _lattice_oriented(message: str) -> bool:
    return _ROUTER.lattice_oriented(message)


def _uav_oriented(message: str) -> bool:
    return _ROUTER.uav_oriented(message)


def _has_cad_tool_intent(message: str) -> bool:
    return _ROUTER.has_cad_tool_intent(message)


def _heuristic_tools(message: str) -> list[dict[str, Any]]:
    return _ROUTER.plan_tools(message)


def _heuristic_next_tool(
    message: str,
    cad_geometry: dict[str, Any] | None,
    cad_results: dict[str, Any] | None,
    tool_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _ROUTER.plan(message, cad_geometry, cad_results, tool_results)


def _cad_state_blob(state: AgentState) -> str:
    """KPI-only summary for the system prompt (F02: keep LLM context compact)."""
    geo = state.get("cad_geometry") or {}
    res = state.get("cad_results") or {}

    def pick(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        return {k: source[k] for k in keys if source.get(k) is not None}

    blob = {
        "geometry": pick(
            geo,
            (
                "part",
                "web_type",
                "cell_size_mm",
                "strut_radius_mm",
                "material",
                "material_id",
                "volume_mm3",
                "mass_kg",
                "relative_density",
                "step_path",
                "fcstd_path",
            ),
        ),
        "results": pick(
            res,
            (
                "part",
                "web_type",
                "method",
                "force_n",
                "mesh_max_size_mm",
                "max_von_mises_mpa",
                "safety_factor_vs_yield",
                "material",
                "material_id",
                "pad_deflection_mm",
                "tip_deflection_mm",
                "fallback",
            ),
        ),
    }
    if not blob["geometry"] and not blob["results"]:
        return "(none)"
    return json.dumps(blob, default=str)


def _tool_specs_to_pending(calls: list[ToolCallSpec] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for call in calls:
        if isinstance(call, ToolCallSpec):
            pending.append({"name": call.name, "args": call.args, "id": call.id})
        else:
            pending.append(
                {
                    "name": str(call.get("name", "")),
                    "args": dict(call.get("args") or {}),
                    "id": str(call.get("id") or f"call_{uuid.uuid4().hex[:10]}"),
                }
            )
    return pending


def _finalize_without_llm(state: AgentState, draft: str = "") -> str:
    parts: list[str] = []
    if draft:
        parts.append(draft)
    citations = state.get("citations") or []
    if citations:
        parts.append("Retrieved context:")
        for c in citations[:4]:
            parts.append(f"- [{c['source']}] {c['text'][:400]}")
        parts.append("Sources:")
        for c in citations[:4]:
            parts.append(f"- {c['source']} (score={c['score']:.3f})")
    tool_results = state.get("tool_results") or []
    if tool_results:
        parts.append("Tool results:")
        for item in tool_results:
            parts.append(f"- {item['name']}: {json.dumps(item.get('result'))[:500]}")
    return "\n\n".join(parts).strip() or "No response generated."


def _add_usage(
    prev: dict[str, int] | None, turn: dict[str, int] | None
) -> dict[str, int] | None:
    """Accumulate per-run token totals (H2). Missing usage degrades to prev/None."""
    if not turn:
        return prev
    out = dict(prev or {})
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        out[key] = int(out.get(key) or 0) + int(turn.get(key) or 0)
    return out


# H2 session token metering: per-thread cumulative totals, keyed like the CAD
# module sessions (thread_id -> totals). In-process only, mirrors _SESSIONS.
_TOKEN_SESSIONS: dict[str, dict[str, int]] = {}


def record_session_usage(thread_id: str, usage: dict[str, int] | None) -> None:
    """Add one finished run's token usage to the thread's session totals."""
    if not usage:
        return
    totals = _TOKEN_SESSIONS.setdefault(
        str(thread_id),
        {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "turns": 0},
    )
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        totals[key] += int(usage.get(key) or 0)
    totals["turns"] += 1


def session_usage() -> dict[str, Any]:
    """Per-thread cumulative token totals plus an all-threads sum (/api/health)."""
    threads = {tid: dict(totals) for tid, totals in _TOKEN_SESSIONS.items()}
    total = {
        key: sum(totals.get(key, 0) for totals in _TOKEN_SESSIONS.values())
        for key in ("input_tokens", "output_tokens", "total_tokens", "turns")
    }
    return {"threads": threads, "total": total}


def reset_token_sessions() -> None:
    _TOKEN_SESSIONS.clear()


def build_graph(
    *,
    llm: LLMProvider | None = None,
    checkpointer: MemorySaver | None = None,
    call_tool_fn: CallToolFn | None = None,
    settings: Settings | None = None,
    require_tool_confirm: bool | None = None,
    max_tool_rounds: int | None = None,
):
    """Build retrieve → agent ⇄ tools graph. Injectables support unit tests."""
    settings = settings or get_settings()
    tool_fn = call_tool_fn or call_tool
    confirm = (
        settings.agent_require_tool_confirm
        if require_tool_confirm is None
        else require_tool_confirm
    )
    max_rounds = (
        settings.agent_max_tool_rounds if max_tool_rounds is None else max_tool_rounds
    )
    lc_tools = get_langchain_tools()
    saver = checkpointer if checkpointer is not None else MemorySaver()

    def node_retrieve(state: AgentState) -> dict[str, Any]:
        message = state.get("message") or ""
        if not message:
            for msg in reversed(state.get("messages") or []):
                if isinstance(msg, HumanMessage):
                    message = _message_content(msg)
                    break
        detail = retrieve_detail(message, k=4) if message else {"fused": [], "grounding": "none"}
        hits = detail.get("fused") or []
        # Seed CAD fields from module session if graph state empty (same process demo)
        cad = get_state()
        updates: dict[str, Any] = {
            "citations": hits,
            "grounding": detail.get("grounding") or "none",
            "message": message,
            "pending_tool_calls": [],
        }
        if state.get("cad_geometry") is None and cad.get("geometry"):
            updates["cad_geometry"] = cad["geometry"]
        if state.get("cad_results") is None and cad.get("results"):
            updates["cad_results"] = cad["results"]
        return updates

    def node_agent(state: AgentState) -> dict[str, Any]:
        visits = int(state.get("agent_visits") or 0) + 1
        iteration = int(state.get("iteration") or 0) + 1
        message = state.get("message") or ""
        citations = state.get("citations") or []
        context = "\n\n".join(
            f"[{c['source']}] (score={c['score']:.3f})\n{c['text']}" for c in citations
        )
        base = {
            "agent_visits": visits,
            "iteration": iteration,
            "pending_tool_calls": [],
        }

        if iteration > max_rounds:
            err = f"Stopped after {max_rounds} tool rounds (agent_max_tool_rounds)."
            return {
                **base,
                "error": err,
                "answer": _finalize_without_llm(state, err),
                "pending_tool_calls": [],
                "messages": [AIMessage(content=err)],
            }

        provider = llm
        use_llm = provider is not None
        if provider is None and settings.llm_configured():
            try:
                provider = get_llm_provider(settings)
                use_llm = True
            except LLMNotConfiguredError:
                use_llm = False

        if use_llm and provider is not None:
            try:
                system = SYSTEM_PROMPT.format(
                    tools=json.dumps(TOOL_SPECS, indent=2),
                    context=context or "(none)",
                    cad_state=_cad_state_blob(state),
                )
                history = list(state.get("messages") or [])
                # Ensure system + latest human are present for this turn.
                # H1: trim the *sent* payload only — the checkpointed history
                # (graph state) keeps every message verbatim.
                msgs: list[BaseMessage] = [SystemMessage(content=system)]
                msgs.extend(
                    condense_history(
                        [m for m in history if not isinstance(m, SystemMessage)]
                    )
                )
                if not any(isinstance(m, HumanMessage) for m in msgs):
                    msgs.append(HumanMessage(content=message))

                turn: AgentTurn = provider.complete_messages(msgs, tools=lc_tools)
                pending = _tool_specs_to_pending(turn.tool_calls)
                usage_totals = _add_usage(state.get("usage"), turn.usage)

                # Assist only when the user asked to run CAD/FEA and the LLM omitted tools.
                if not pending and visits == 1 and _has_cad_tool_intent(message):
                    pending = _tool_specs_to_pending(
                        _heuristic_next_tool(
                            message,
                            state.get("cad_geometry"),
                            state.get("cad_results"),
                            state.get("tool_results") or [],
                        )
                    )

                ai_kwargs: dict[str, Any] = {"content": turn.content or ""}
                if pending:
                    ai_kwargs["tool_calls"] = [
                        {
                            "id": p["id"],
                            "name": p["name"],
                            "args": p["args"],
                            "type": "tool_call",
                        }
                        for p in pending
                    ]
                updates: dict[str, Any] = {
                    **base,
                    "pending_tool_calls": pending,
                    "usage": usage_totals,
                    "messages": [AIMessage(**ai_kwargs)],
                }
                if not pending:
                    updates["answer"] = turn.content or _finalize_without_llm(state)
                return updates
            except LLMNotConfiguredError as exc:
                return {
                    **base,
                    "error": str(exc),
                    "answer": str(exc),
                    "messages": [AIMessage(content=str(exc))],
                }

        # No LLM: heuristic one-tool-at-a-time loop (H6 offline mode, gated by
        # settings.heuristic_fallback — default on).
        pending = []
        draft = (
            "LLM API key not configured yet. Running heuristic tool routing so CAD/FEA "
            "tools and RAG still work. Add GEMINI_API_KEY to .env for full chat."
        )
        if settings.heuristic_fallback:
            pending = _tool_specs_to_pending(
                _heuristic_next_tool(
                    message,
                    state.get("cad_geometry"),
                    state.get("cad_results"),
                    state.get("tool_results") or [],
                )
            )
        else:
            draft = (
                "LLM API key not configured and heuristic fallback is disabled "
                "(HEURISTIC_FALLBACK=false), so no CAD/FEA tools can run. "
                "Add GEMINI_API_KEY to .env for full chat."
            )
        ai_kwargs = {"content": draft}
        if pending:
            ai_kwargs["tool_calls"] = [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "args": p["args"],
                    "type": "tool_call",
                }
                for p in pending
            ]
        updates = {
            **base,
            "pending_tool_calls": pending,
            "messages": [AIMessage(**ai_kwargs)],
        }
        if not pending:
            updates["answer"] = _finalize_without_llm(state, draft)
        return updates

    def node_tools(state: AgentState) -> dict[str, Any]:
        pending = list(state.get("pending_tool_calls") or [])
        visits = int(state.get("tools_node_visits") or 0) + 1
        if not pending:
            return {"tools_node_visits": visits, "pending_tool_calls": []}

        needs_confirm = confirm and any(
            p.get("name") in FREECAD_MUTATING_TOOLS for p in pending
        )
        if needs_confirm:
            decision = interrupt(
                {
                    "action": "confirm_tools",
                    "tool_calls": pending,
                    "message": "OK to run FreeCAD tool(s)?",
                }
            )
            approved = decision is True or (
                isinstance(decision, dict) and decision.get("approved") is True
            )
            if not approved:
                cancelled = []
                tool_messages = []
                for p in pending:
                    result = outcome.envelope(
                        {
                            "ok": False,
                            "cancelled": True,
                            "error": "User rejected FreeCAD tool confirmation.",
                            "error_class": "user_cancelled",
                        },
                        tool=str(p.get("name") or "freecad_tools"),
                        elapsed_s=0.0,
                    )
                    cancelled.append(
                        {"name": p["name"], "args": p.get("args") or {}, "result": result}
                    )
                    tool_messages.append(
                        ToolMessage(
                            content=json.dumps(result),
                            tool_call_id=p.get("id") or p["name"],
                            name=p["name"],
                        )
                    )
                prior = list(state.get("tool_results") or [])
                return {
                    "tools_node_visits": visits,
                    "pending_tool_calls": [],
                    "tool_results": prior + cancelled,
                    "messages": tool_messages,
                    "answer": "Cancelled: FreeCAD tool(s) were not executed.",
                }

        new_results: list[dict[str, Any]] = []
        tool_messages: list[ToolMessage] = []

        for p in pending:
            name = str(p.get("name", ""))
            args = dict(p.get("args") or {})
            result = tool_fn(name, args)
            new_results.append({"name": name, "args": args, "result": result})
            tool_messages.append(
                ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=str(p.get("id") or name),
                    name=name,
                )
            )

        # H4: node_tools no longer mirrors geometry/results into graph state —
        # the CAD module session (_SESSIONS via _STATE) stays the single
        # authoritative writer, and sync_cad_state is the only graph-side
        # writer pulling from it.

        prior = list(state.get("tool_results") or [])
        return {
            "tools_node_visits": visits,
            "pending_tool_calls": [],
            "tool_results": prior + new_results,
            "messages": tool_messages,
        }

    def node_sync_cad_state(state: AgentState) -> dict[str, Any]:
        # H4: the only graph-side writer of cad_geometry/cad_results — it
        # mirrors the authoritative CAD module session into graph state.
        session = get_state()
        updates: dict[str, Any] = {}
        if session.get("geometry") is not None:
            updates["cad_geometry"] = session["geometry"]
        if session.get("results") is not None:
            updates["cad_results"] = session["results"]
        return updates

    def route_after_agent(state: AgentState) -> str:
        if state.get("error") and not (state.get("pending_tool_calls") or []):
            return END
        pending = state.get("pending_tool_calls") or []
        iteration = int(state.get("iteration") or 0)
        if pending and iteration <= max_rounds:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("retrieve", node_retrieve)
    graph.add_node("agent", node_agent)
    graph.add_node("tools", node_tools)
    graph.add_node("sync_cad_state", node_sync_cad_state)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "sync_cad_state")
    graph.add_edge("sync_cad_state", "agent")
    return graph.compile(checkpointer=saver)


def _message_content(msg: BaseMessage) -> str:
    content = msg.content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content or "")


_GRAPH = None


def reset_graph() -> None:
    global _GRAPH
    _GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def _extract_interrupt(result: dict[str, Any] | Any) -> Any | None:
    if isinstance(result, dict) and "__interrupt__" in result:
        return result["__interrupt__"]
    return None


def _serialize_interrupt(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        out = []
        for item in raw:
            value = getattr(item, "value", item)
            out.append(value)
        return out
    return getattr(raw, "value", raw)


def run_agent(
    message: str = "",
    *,
    thread_id: str | None = None,
    resume: Any | None = None,
    graph=None,
) -> dict[str, Any]:
    """Invoke the agent. Pass resume= to continue after HITL interrupt."""
    compiled = graph or get_graph()
    tid = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": tid}}

    with cad_thread_scope(tid):
        if resume is not None:
            final = compiled.invoke(Command(resume=resume), config)
        else:
            final = compiled.invoke(
                {
                    "message": message,
                    "messages": [HumanMessage(content=message)],
                    "tool_results": [],
                    "pending_tool_calls": [],
                    "iteration": 0,
                    "agent_visits": 0,
                    "tools_node_visits": 0,
                    "usage": None,
                },
                config,
            )

    interrupt_raw = _extract_interrupt(final)
    interrupted = interrupt_raw is not None
    answer = ""
    if isinstance(final, dict):
        answer = final.get("answer") or ""
        if not answer and not interrupted:
            # Last AI message without pending tools
            for msg in reversed(final.get("messages") or []):
                if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                    answer = _message_content(msg)
                    break

    usage = final.get("usage") if isinstance(final, dict) else None
    record_session_usage(tid, usage)

    return {
        "answer": answer,
        "usage": usage,
        "citations": (final.get("citations") if isinstance(final, dict) else None) or [],
        "grounding": (final.get("grounding") if isinstance(final, dict) else None) or "none",
        "tool_calls": (final.get("pending_tool_calls") if isinstance(final, dict) else None)
        or [],
        "tool_results": (final.get("tool_results") if isinstance(final, dict) else None)
        or [],
        "cad_geometry": final.get("cad_geometry") if isinstance(final, dict) else None,
        "cad_results": final.get("cad_results") if isinstance(final, dict) else None,
        "error": final.get("error") if isinstance(final, dict) else None,
        "llm_configured": get_settings().llm_configured(),
        "thread_id": tid,
        "interrupted": interrupted,
        "interrupt": _serialize_interrupt(interrupt_raw),
        "agent_visits": (final.get("agent_visits") if isinstance(final, dict) else None) or 0,
        "tools_node_visits": (
            final.get("tools_node_visits") if isinstance(final, dict) else None
        )
        or 0,
    }


def stream_agent(
    message: str,
    *,
    thread_id: str | None = None,
    resume: Any | None = None,
    graph=None,
) -> Iterator[dict[str, Any]]:
    """Yield stream events (updates mode) then a final payload."""
    compiled = graph or get_graph()
    tid = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": tid}}

    with cad_thread_scope(tid):
        if resume is not None:
            stream_input: Any = Command(resume=resume)
        else:
            stream_input = {
                "message": message,
                "messages": [HumanMessage(content=message)],
                "tool_results": [],
                "pending_tool_calls": [],
                "iteration": 0,
                "agent_visits": 0,
                "tools_node_visits": 0,
                "usage": None,
            }

        yield from _stream_agent_events(compiled, stream_input, config, tid)
        return


def _stream_agent_events(compiled, stream_input: Any, config: dict[str, Any], tid: str):
    for update in compiled.stream(stream_input, config, stream_mode="updates"):
        # update is {node_name: state_delta}
        if isinstance(update, dict):
            for node_name, delta in update.items():
                event: dict[str, Any] = {"type": "node", "node": node_name, "thread_id": tid}
                if isinstance(delta, dict):
                    if delta.get("pending_tool_calls"):
                        event["pending_tool_calls"] = delta["pending_tool_calls"]
                    if delta.get("tool_results"):
                        # only the latest batch names for narration
                        names = [t.get("name") for t in delta["tool_results"][-3:]]
                        event["tools"] = names
                        event["status"] = (
                            f"Running {names[-1]}…" if names else f"{node_name}…"
                        )
                    elif node_name == "retrieve":
                        event["status"] = "Retrieving docs…"
                    elif node_name == "agent":
                        event["status"] = "Thinking…"
                    elif node_name == "tools":
                        event["status"] = "Running tools…"
                    elif node_name == "sync_cad_state":
                        event["status"] = "Updating CAD session state…"
                    else:
                        event["status"] = f"{node_name}…"
                yield event

    # Final snapshot via get_state
    snap = compiled.get_state(config)
    values = snap.values if snap else {}
    interrupt_raw = None
    if snap and getattr(snap, "tasks", None):
        for task in snap.tasks:
            inter = getattr(task, "interrupts", None)
            if inter:
                interrupt_raw = inter
                break

    yield {
        "type": "final",
        "thread_id": tid,
        "answer": values.get("answer") or "",
        "citations": values.get("citations") or [],
        "grounding": values.get("grounding") or "none",
        "tool_results": values.get("tool_results") or [],
        "cad_geometry": values.get("cad_geometry"),
        "cad_results": values.get("cad_results"),
        "error": values.get("error"),
        "interrupted": interrupt_raw is not None,
        "interrupt": _serialize_interrupt(interrupt_raw),
        "agent_visits": values.get("agent_visits") or 0,
        "tools_node_visits": values.get("tools_node_visits") or 0,
        "llm_configured": get_settings().llm_configured(),
    }
