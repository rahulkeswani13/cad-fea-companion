"""H1: send-time context trimming (condense_history) unit + integration."""

from __future__ import annotations

import json

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.memory import MemorySaver

from companion.agent.context import DEFAULT_KEEP_LAST, condense_history, receipt_line
from companion.agent.graph import build_graph, run_agent
from companion.llm.providers import AgentTurn
from tests.fakes import ScriptedLLMProvider


def _tool_msg(idx: int, name: str = "create_brake_pedal", ok: bool = True) -> ToolMessage:
    payload = {
        "ok": ok,
        "part": "brake_pedal",
        "mass_kg": 0.13,
        "receipt": {"tool": name, "elapsed_s": 1.234, "changed": []},
    }
    return ToolMessage(
        content=json.dumps(payload),
        tool_call_id=f"call_{idx}",
        name=name,
    )


def test_recent_window_kept_verbatim():
    msgs = [_tool_msg(i) for i in range(30)]
    out = condense_history(msgs)
    assert len(out) == len(msgs)
    # Last DEFAULT_KEEP_LAST messages are untouched objects.
    for sent, orig in zip(out[-DEFAULT_KEEP_LAST:], msgs[-DEFAULT_KEEP_LAST:]):
        assert sent is orig
    # Older tool results were condensed (not the same object).
    for sent in out[:-DEFAULT_KEEP_LAST]:
        assert sent is not None
        assert str(sent.content).startswith("receipt(")


def test_older_tool_results_collapse_to_receipts():
    msgs = [HumanMessage(content=f"turn {i}") for i in range(5)]
    msgs.insert(0, _tool_msg(0))
    out = condense_history(msgs, keep_last=3)
    assert str(out[0].content).startswith("receipt(")
    for sent in out[-3:]:
        assert sent is msgs[len(msgs) - 3 + out[-3:].index(sent)] or str(
            sent.content
        ) == str(msgs[len(msgs) - 3 + out[-3:].index(sent)].content)


def test_receipt_shape_tool_ok_elapsed_keys():
    msg = _tool_msg(0)
    line = receipt_line(msg)
    assert line.startswith("receipt(")
    assert "tool=create_brake_pedal" in line
    assert "ok=true" in line
    assert "elapsed_s=1.234" in line
    # KPI key names ride along; values must not.
    assert "keys=mass_kg,part" in line
    assert "0.13" not in line


def test_receipt_failed_result_and_malformed_payload():
    failed = ToolMessage(
        content=json.dumps(
            {"ok": False, "error": "boom", "receipt": {"tool": "x", "elapsed_s": 0.5}}
        ),
        tool_call_id="call_x",
        name="apply_load_and_solve",
    )
    line = receipt_line(failed)
    assert "tool=apply_load_and_solve" in line
    assert "ok=false" in line
    assert "boom" not in line  # error text must not re-enter context

    malformed = ToolMessage(content="not json", tool_call_id="c", name="t")
    fallback = receipt_line(malformed)
    assert fallback.startswith("receipt(tool=t ok=false)")


def test_human_ai_turns_and_current_turn_never_trimmed():
    msgs: list = []
    for i in range(40):
        msgs.append(HumanMessage(content=f"question {i}"))
        msgs.append(AIMessage(content=f"answer {i}"))
    msgs.append(HumanMessage(content="the current question"))
    out = condense_history(msgs, keep_last=20)
    # Every human/AI turn survives verbatim regardless of age.
    humans = [m for m in out if isinstance(m, HumanMessage)]
    assert [str(m.content) for m in humans] == [f"question {i}" for i in range(40)] + [
        "the current question"
    ]
    assert str(out[-1].content) == "the current question"


def test_condense_is_pure_input_untouched():
    msgs = [_tool_msg(0), HumanMessage(content="hi"), AIMessage(content="hello")]
    snapshot = [str(m.content) for m in msgs]
    condense_history(msgs, keep_last=1)
    assert [str(m.content) for m in msgs] == snapshot


def test_node_agent_sends_condensed_payload_checkpoint_stays_full():
    """Send-time only: LLM sees receipts for old tool results, state keeps them."""
    tools = StubToolsSeq()
    llm = ScriptedLLMProvider(
        turns=[
            AgentTurn(content="create", tool_calls=[tools.tc_create]),
            AgentTurn(content="done", tool_calls=[]),
        ]
    )
    g = build_graph(
        llm=llm,
        call_tool_fn=tools,
        checkpointer=MemorySaver(),
        require_tool_confirm=False,
    )
    out = run_agent("create a cantilever beam", thread_id="ctx-trim", graph=g)
    assert out["answer"]
    # First payload: no history yet.
    first, second = llm.calls[0], llm.calls[1]
    assert not any(isinstance(m, ToolMessage) for m in first)
    # Second payload carries the create tool result...
    tool_msgs = [m for m in second if isinstance(m, ToolMessage)]
    assert tool_msgs, "second turn must include the tool result message"
    # Checkpointed state keeps the full verbatim payload...
    snap = g.get_state({"configurable": {"thread_id": "ctx-trim"}})
    state_tool_msgs = [
        m for m in snap.values.get("messages") or [] if isinstance(m, ToolMessage)
    ]
    assert state_tool_msgs
    assert json.loads(state_tool_msgs[0].content)["ok"] is True


def StubToolsSeq():
    from tests.fakes import StubTools, tc

    stub = StubTools()
    stub.tc_create = tc("create_cantilever", {"length_mm": 100})
    return stub


def test_system_message_slot_untouched():
    out = condense_history(
        [SystemMessage(content="sys"), _tool_msg(1), HumanMessage(content="q")],
        keep_last=1,
    )
    assert isinstance(out[0], SystemMessage)
    assert isinstance(out[1], ToolMessage)
    assert str(out[1].content).startswith("receipt(")
