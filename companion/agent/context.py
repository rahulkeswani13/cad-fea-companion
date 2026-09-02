"""H1 send-time context trimming.

Long multi-turn sessions accumulate full tool-result payloads in checkpointed
history. Sending every one of them to the LLM wastes tokens on stale data.
`condense_history` builds the *send-time* payload: the last ``keep_last``
messages stay verbatim, older ToolMessages collapse to one deterministic
receipt line (tool, ok, elapsed, KPI key names), and human/AI turns are kept
verbatim so multi-turn memory survives.

Pure module: input messages are never mutated and the checkpointed graph
state is untouched — trimming happens only where the LLM payload is built
(``node_agent``). The receipt deliberately carries key *names*, not values:
stale KPI values must not masquerade as current ones (solver honesty).
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import BaseMessage, ToolMessage

DEFAULT_KEEP_LAST = 20

# Envelope/bookkeeping keys excluded from the KPI-key list in a receipt —
# they describe the envelope, not the result data.
_NON_KPI_KEYS = frozenset(
    {"ok", "error", "error_class", "correction", "debug_ref", "receipt"}
)


def receipt_line(msg: ToolMessage) -> str:
    """One-line deterministic receipt for an older tool result.

    Shape: ``receipt(tool=<name> ok=<bool> elapsed_s=<s> keys=<k1,k2,...>)``.
    Malformed/oversized payloads degrade to a bare ``receipt(tool=... ok=...)``
    line — this must never raise.
    """
    name = getattr(msg, "name", None) or "tool"
    payload: dict[str, Any] = {}
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                payload = data
        except json.JSONDecodeError:
            payload = {}
    ok = bool(payload.get("ok", False))
    parts = [f"tool={name}", f"ok={str(ok).lower()}"]
    receipt = payload.get("receipt")
    elapsed = receipt.get("elapsed_s") if isinstance(receipt, dict) else None
    if isinstance(elapsed, (int, float)):
        parts.append(f"elapsed_s={round(float(elapsed), 3)}")
    kpi_keys = sorted(k for k in payload if k not in _NON_KPI_KEYS)
    if kpi_keys:
        parts.append("keys=" + ",".join(kpi_keys))
    return "receipt(" + " ".join(parts) + ")"


def condense_history(
    messages: list[BaseMessage],
    keep_last: int = DEFAULT_KEEP_LAST,
) -> list[BaseMessage]:
    """Return a trimmed copy of ``messages`` for the LLM payload.

    - The last ``keep_last`` messages are kept verbatim (the current turn is
      always inside the window for any realistic ``keep_last``).
    - Older ToolMessages become ToolMessages whose content is their receipt
      line (same tool_call_id/name, so provider role pairing stays valid).
    - All other messages pass through verbatim.
    """
    if keep_last < 0:
        keep_last = 0
    trimmed: list[BaseMessage] = []
    boundary = len(messages) - keep_last
    for idx, msg in enumerate(messages):
        if idx >= boundary or not isinstance(msg, ToolMessage):
            trimmed.append(msg)
            continue
        trimmed.append(
            ToolMessage(
                content=receipt_line(msg),
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
        )
    return trimmed
