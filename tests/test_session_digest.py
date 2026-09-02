"""H12: deterministic session digest — bounded tool-receipt timeline in the
CAD-state blob (offline-first replacement for LLM summarization)."""

from __future__ import annotations

import json

from companion.agent.graph import DIGEST_MAX_TOOLS, _cad_state_blob


def _tool_result(name: str, ok: bool = True, elapsed: float = 1.0) -> dict:
    return {
        "name": name,
        "args": {},
        "result": {
            "ok": ok,
            "receipt": {"tool": name, "elapsed_s": elapsed, "changed": []},
        },
    }


def test_digest_includes_recent_tool_receipts():
    blob = json.loads(
        _cad_state_blob(
            {
                "tool_results": [
                    _tool_result("create_cantilever", elapsed=2.5),
                    _tool_result("apply_load_and_solve", elapsed=9.1),
                ]
            }
        )
    )
    assert blob["recent_tools"] == [
        {"tool": "create_cantilever", "ok": True, "elapsed_s": 2.5},
        {"tool": "apply_load_and_solve", "ok": True, "elapsed_s": 9.1},
    ]


def test_digest_is_bounded_to_last_n():
    tool_results = [_tool_result(f"tool_{i:02d}") for i in range(40)]
    blob = json.loads(_cad_state_blob({"tool_results": tool_results}))
    names = [entry["tool"] for entry in blob["recent_tools"]]
    assert len(names) == DIGEST_MAX_TOOLS
    assert names == [f"tool_{i:02d}" for i in range(40 - DIGEST_MAX_TOOLS, 40)]


def test_digest_carries_flags_not_values():
    """Honesty: the digest says what ran and whether it worked — it must not
    resurrect stale KPI values that H1 condensed out of the message history."""
    item = _tool_result("apply_load_and_solve")
    item["result"]["max_von_mises_mpa"] = 118.2  # KPI must not leak into digest
    blob_str = _cad_state_blob({"tool_results": [item]})
    assert "118.2" not in blob_str
    parsed = json.loads(blob_str)
    assert parsed["recent_tools"][0]["ok"] is True


def test_digest_empty_state_still_none_marker():
    assert _cad_state_blob({}) == "(none)"
    assert _cad_state_blob({"tool_results": []}) == "(none)"


def test_failed_tool_shows_ok_false():
    blob = json.loads(
        _cad_state_blob({"tool_results": [_tool_result("apply_load_and_solve", ok=False)]})
    )
    assert blob["recent_tools"][0]["ok"] is False
