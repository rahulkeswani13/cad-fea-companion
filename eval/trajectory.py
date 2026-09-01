"""Deterministic trajectory checks over agent tool_results (evals plan phase 1).

These complement the LLM judge: they cost nothing, never flake, and encode
mechanical expectations about *how* the agent worked — not just what it
answered. All checkers take the `tool_results` list shape produced by
`companion.agent.graph.run_agent` (items: {name, args, result}) and return a
list of human-readable failure strings (empty = pass).
"""

from __future__ import annotations

import json
from typing import Any


def _ok_results(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only successful, non-cancelled tool calls participate in checks."""
    out = []
    for item in tool_results or []:
        result = item.get("result") or {}
        if result.get("ok") is False or result.get("cancelled"):
            continue
        out.append(item)
    return out


def check_tool_order(
    tool_results: list[dict[str, Any]], before: str, after: str
) -> list[str]:
    """`before` must appear (successfully) somewhere before `after`."""
    names = [str(item.get("name")) for item in _ok_results(tool_results)]
    if after not in names:
        return []  # `after` never ran — ordering is vacuous, not violated
    if before not in names:
        return [f"tool order: {after!r} ran without {before!r} before it"]
    if names.index(before) > names.index(after):
        return [f"tool order: {before!r} ran after {after!r}"]
    return []


def check_no_noop_repeat(tool_results: list[dict[str, Any]]) -> list[str]:
    """Flag the same tool called 2+ times with identical args, all succeeding.

    A retry after a failure is legitimate; back-to-back successful identical
    calls are wasted rounds.
    """
    seen: dict[tuple[str, str], int] = {}
    failures: list[str] = []
    for item in _ok_results(tool_results):
        key = (str(item.get("name")), json.dumps(item.get("args") or {}, sort_keys=True))
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            failures.append(f"noop repeat: {item.get('name')!r} called twice with identical args")
    return failures


def check_max_rounds(
    tool_results: list[dict[str, Any]], max_rounds: int
) -> list[str]:
    """No run should execute more tools than agent_max_tool_rounds allows."""
    count = len(_ok_results(tool_results))
    if count > max_rounds:
        return [f"max rounds: {count} successful tool calls exceeds limit {max_rounds}"]
    return []


def run_trajectory_checks(
    case: dict[str, Any], tool_results: list[dict[str, Any]]
) -> list[str]:
    """Run every trajectory check requested by an agent case's fields."""
    failures: list[str] = []
    order = case.get("expect_tool_order") or {}
    if isinstance(order, dict) and order.get("before") and order.get("after"):
        failures += check_tool_order(
            tool_results, str(order["before"]), str(order["after"])
        )
    if case.get("expect_no_repeat_tools"):
        failures += check_no_noop_repeat(tool_results)
    if case.get("expect_max_rounds") is not None:
        failures += check_max_rounds(tool_results, int(case["expect_max_rounds"]))
    return failures
