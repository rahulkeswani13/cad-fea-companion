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


def _pedal_oriented(message: str) -> bool:
    lower = message.lower()
    return any(
        k in lower
        for k in (
            "brake pedal",
            "brake-pedal",
            "pedal",
            "footpad",
            "pushrod",
            "clevis",
            "pivot hole",
        )
    )


def _lattice_oriented(message: str) -> bool:
    lower = message.lower()
    return any(
        k in lower
        for k in (
            "lattice",
            "bcc",
            "fcc",
            "xtruss",
            "x-truss",
            "x truss",
            "truss",
            "relative density",
            "bracket",
        )
    )


def _uav_oriented(message: str) -> bool:
    lower = message.lower()
    return any(
        k in lower
        for k in (
            "uav",
            "drone",
            "quadcopter",
            "quad-copter",
            "motor mount",
            "motor-mount",
            "motor ring",
        )
    )


def _has_cad_tool_intent(message: str) -> bool:
    """True when the user asked to mutate CAD/FEA, not just ask a docs question."""
    lower = message.lower()
    return any(
        k in lower
        for k in (
            "create",
            "make",
            "build",
            "rebuild",
            "generate",
            "solve",
            "apply",
            "compare",
            "which lattice",
            "which variant",
            "lightest",
            "run fea",
            "run fem",
            "static analysis",
            "open freecad",
            "launch freecad",
            "show in freecad",
            "open the latest model",
            "lattice metrics",
            "get_lattice",
            "get_max_von_mises",
        )
    )


def _heuristic_tools(message: str) -> list[dict[str, Any]]:
    lower = message.lower()
    calls: list[dict[str, Any]] = []

    wants_create_kw = any(
        k in lower for k in ("create", "make", "build", "generate", "rebuild")
    )
    uav = _uav_oriented(lower)
    wants_pedal = _pedal_oriented(lower) and wants_create_kw and not uav
    # Default lattice → brake pedal (UAV arms own their lattice routing).
    wants_lattice_default = _lattice_oriented(lower) and wants_create_kw and not uav
    if wants_pedal or wants_lattice_default:
        args: dict[str, Any] = {}
        if "fcc" in lower:
            args["web_type"] = "fcc"
        elif (
            "solid" in lower
            and "xtruss" not in lower
            and "truss" not in lower
            and "bcc" not in lower
        ):
            args["web_type"] = "solid"
        else:
            # Default lattice fill for pedal is 2.5D X-truss (bcc aliases here).
            args["web_type"] = "xtruss"
        calls.append({"name": "create_brake_pedal", "args": args})

    # F26: UAV arm flagship part. Default web is solid (the demo baseline);
    # lattice/truss wording upgrades it to the X-truss web.
    if uav and wants_create_kw:
        args_u: dict[str, Any] = {}
        if any(k in lower for k in ("xtruss", "x-truss", "x truss", "truss", "lattice", "bcc")):
            args_u["web_type"] = "xtruss"
        elif "solid" in lower:
            args_u["web_type"] = "solid"
        calls.append({"name": "create_uav_arm", "args": args_u})

    wants_compare = any(
        k in lower
        for k in (
            "compare",
            "which lattice",
            "which variant",
            "best lattice",
            "lightest",
            "recommend",
        )
    ) and (
        _pedal_oriented(lower)
        or _lattice_oriented(lower)
        or "solid" in lower
        or "variant" in lower
    )
    if wants_compare:
        calls.append({"name": "compare_brake_pedal_variants", "args": {}})

    # F09: material questions. "Ti vs Al" style questions compare the table;
    # "switch to Ti" style edits go through the design program.
    _MATERIAL_HINTS = (
        "material",
        "titanium",
        "ti-6al",
        "ti6al",
        " ti ",
        " ti64",
        "7075",
        "6061",
        "pa12",
        "nylon",
        "aluminum",
        "aluminium",
        "steel",
        "alloy",
    )
    mentions_material = any(k in lower for k in _MATERIAL_HINTS)
    if mentions_material:
        mentioned = None
        for token in re.findall(r"[A-Za-z0-9-]+", lower):
            record = mats.get_material(token)
            if record:
                mentioned = record["id"]
                break
        wants_set_material = any(
            k in lower
            for k in ("switch", "make it", "change to", "convert", "set the material")
        )
        wants_material_compare = any(
            k in lower
            for k in ("compare", " vs ", "versus", "which material", "better", "what about")
        )
        if mentioned and wants_set_material:
            calls.append(
                {"name": "update_design_program", "args": {"changes": {"material": mentioned}}}
            )
        elif wants_material_compare or mentioned is None:
            calls.append({"name": "compare_materials", "args": {}})

    wants_metrics = any(
        k in lower
        for k in ("lattice metrics", "mass estimate", "get_lattice", "get lattice metrics")
    )
    if wants_metrics:
        calls.append({"name": "get_lattice_metrics", "args": {}})

    wants_create = any(
        k in lower for k in ("create", "make a cantilever", "build a beam", "cantilever")
    ) and any(k in lower for k in ("create", "make", "build", "mm", "x"))
    if (
        not _pedal_oriented(lower)
        and not _lattice_oriented(lower)
        and not _uav_oriented(lower)
        and (wants_create or ("cantilever" in lower and "x" in lower))
    ):
        args_c: dict[str, Any] = {}
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)",
            lower,
        )
        if m:
            args_c = {
                "length_mm": float(m.group(1)),
                "width_mm": float(m.group(2)),
                "height_mm": float(m.group(3)),
            }
        if "create" in lower or "make" in lower or "build" in lower or args_c:
            calls.append({"name": "create_cantilever", "args": args_c})

    wants_convergence = any(
        k in lower
        for k in (
            "convergence",
            "converged",
            "mesh study",
            "mesh sensitivity",
            "mesh refinement",
            "refine the mesh",
            "run_convergence_study",
        )
    )
    if wants_convergence:
        args_cv: dict[str, Any] = {}
        fm_cv = re.search(r"(\d+(?:\.\d+)?)\s*n\b", lower)
        if fm_cv:
            args_cv["force_n"] = float(fm_cv.group(1))
        calls.append({"name": "run_convergence_study", "args": args_cv})

    wants_solve = any(
        k in lower
        for k in (
            "apply",
            "solve",
            "run fea",
            "run fem",
            "tip load",
            "static analysis",
            "100 n",
            "100n",
            "500 n",
            "500n",
            "20000 n",
            "20000n",
            "2000 n",
            "2000n",
            "pad load",
            "footpad",
        )
    )
    if wants_solve:
        args_s: dict[str, Any] = {}
        fm = re.search(r"(\d+(?:\.\d+)?)\s*n\b", lower)
        if fm:
            args_s["force_n"] = float(fm.group(1))
        calls.append({"name": "apply_load_and_solve", "args": args_s})

    wants_stress = any(
        k in lower
        for k in (
            "von mises",
            "max stress",
            "maximum stress",
            "under 50",
            "get_max_von_mises",
            "safety factor",
            "concentrated",
        )
    )
    if wants_stress:
        calls.append({"name": "get_max_von_mises", "args": {}})

    if any(
        k in lower
        for k in (
            "open freecad",
            "launch freecad",
            "show in freecad",
            "open the latest model",
            "open free cad",
        )
    ):
        calls.append({"name": "open_in_freecad", "args": {}})
    return calls


def _done_tool_names(tool_results: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in tool_results:
        result = item.get("result") or {}
        if result.get("ok") is False:
            continue
        if result.get("cancelled"):
            continue
        names.add(str(item.get("name", "")))
    return names


def _heuristic_next_tool(
    message: str,
    cad_geometry: dict[str, Any] | None,
    cad_results: dict[str, Any] | None,
    tool_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return at most one next tool so the agent loop can observe results."""
    planned = _heuristic_tools(message)
    lower = message.lower()
    if not planned and any(
        k in lower
        for k in (
            "create",
            "solve",
            "cantilever",
            "von mises",
            "lattice",
            "pedal",
            "brake",
            "bcc",
            "fcc",
            "compare",
            "uav",
            "drone",
        )
    ):
        planned = _heuristic_tools(message)

    done = _done_tool_names(tool_results)
    failed = {
        str(item.get("name"))
        for item in tool_results
        if (item.get("result") or {}).get("ok") is False
        and not (item.get("result") or {}).get("cancelled")
    }
    explicit_create = any(k in lower for k in ("create", "make", "build", "rebuild"))
    pedalist = _pedal_oriented(lower) or _lattice_oriented(lower)
    uavist = _uav_oriented(lower)

    for call in planned:
        name = call["name"]
        if name == "create_brake_pedal":
            if cad_geometry and not explicit_create and name not in failed:
                continue
            if name in done and name not in failed:
                continue
            return [call]
        if name == "create_uav_arm":
            if cad_geometry and not explicit_create and name not in failed:
                continue
            if name in done and name not in failed:
                continue
            return [call]
        if name == "create_cantilever":
            if cad_geometry and not explicit_create and name not in failed:
                continue
            if name in done and name not in failed:
                continue
            return [call]
        if name == "apply_load_and_solve":
            created = (
                "create_brake_pedal" in done
                or "create_uav_arm" in done
                or "create_cantilever" in done
            )
            if not cad_geometry and not created:
                if uavist:
                    return [{"name": "create_uav_arm", "args": {"web_type": "solid"}}]
                if pedalist:
                    return [{"name": "create_brake_pedal", "args": {"web_type": "xtruss"}}]
                return [{"name": "create_cantilever", "args": {}}]
            if name in done and name not in failed and cad_results:
                continue
            return [call]
        if name in (
            "get_lattice_metrics",
            "compare_brake_pedal_variants",
            "compare_materials",
        ):
            if name == "get_lattice_metrics" and not cad_geometry:
                if "create_brake_pedal" not in done:
                    return [{"name": "create_brake_pedal", "args": {"web_type": "xtruss"}}]
            # compare_materials works from stored/precomputed runs — no live
            # geometry required, so it falls through without a create.
            if name in done:
                continue
            return [call]
        if name == "update_design_program":
            created = (
                "create_brake_pedal" in done
                or "create_uav_arm" in done
                or "create_cantilever" in done
            )
            if not cad_geometry and not created:
                if uavist:
                    return [{"name": "create_uav_arm", "args": {"web_type": "solid"}}]
                if pedalist:
                    return [{"name": "create_brake_pedal", "args": {"web_type": "xtruss"}}]
                return [{"name": "create_cantilever", "args": {}}]
            if name in done and name not in failed:
                continue
            return [call]
        if name == "run_convergence_study":
            created = (
                "create_brake_pedal" in done
                or "create_uav_arm" in done
                or "create_cantilever" in done
            )
            if not cad_geometry and not created:
                if uavist:
                    return [{"name": "create_uav_arm", "args": {"web_type": "solid"}}]
                if pedalist:
                    return [{"name": "create_brake_pedal", "args": {"web_type": "xtruss"}}]
                return [{"name": "create_cantilever", "args": {}}]
            if name in done and name not in failed:
                continue
            return [call]
        if name == "get_max_von_mises":
            if name in done:
                continue
            return [call]
        if name == "open_in_freecad":
            if name in done:
                continue
            return [call]
    return []


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
                # Ensure system + latest human are present for this turn
                msgs: list[BaseMessage] = [SystemMessage(content=system)]
                # Drop prior system messages from history; keep human/ai/tool
                for m in history:
                    if isinstance(m, SystemMessage):
                        continue
                    msgs.append(m)
                if not any(isinstance(m, HumanMessage) for m in msgs):
                    msgs.append(HumanMessage(content=message))

                turn: AgentTurn = provider.complete_messages(msgs, tools=lc_tools)
                pending = _tool_specs_to_pending(turn.tool_calls)

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

        # No LLM: heuristic one-tool-at-a-time loop
        pending = _tool_specs_to_pending(
            _heuristic_next_tool(
                message,
                state.get("cad_geometry"),
                state.get("cad_results"),
                state.get("tool_results") or [],
            )
        )
        draft = (
            "LLM API key not configured yet. Running heuristic tool routing so CAD/FEA "
            "tools and RAG still work. Add GEMINI_API_KEY to .env for full chat."
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
        geometry = state.get("cad_geometry")
        results = state.get("cad_results")

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
            # Mirror important CAD facts into graph state
            if name in (
                "create_cantilever",
                "create_brake_pedal",
            ) and result.get("ok"):
                geometry = result
            if name == "apply_load_and_solve" and result.get("ok"):
                results = result
            if name == "get_max_von_mises" and result.get("ok"):
                results = {**(results or {}), **result}
            if name in (
                "get_lattice_metrics",
                "compare_brake_pedal_variants",
                "compare_materials",
            ) and result.get("ok"):
                # Keep geometry; metrics/compare are observational.
                pass

        # Also pull module _STATE after tools (production path)
        session = get_state()
        if session.get("geometry"):
            geometry = session["geometry"]
        if session.get("results"):
            results = session["results"]

        prior = list(state.get("tool_results") or [])
        return {
            "tools_node_visits": visits,
            "pending_tool_calls": [],
            "tool_results": prior + new_results,
            "cad_geometry": geometry,
            "cad_results": results,
            "messages": tool_messages,
        }

    def node_sync_cad_state(state: AgentState) -> dict[str, Any]:
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

    return {
        "answer": answer,
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
