"""H5 eval history: append-only trend for eval runs.

Each ``run_eval.py`` execution appends one compact entry to
``data/results/eval_history.jsonl`` and prints its delta against the
previous entry — evals trend, they don't just gate. Local-only by design
(plan: CI artifacts for history are explicitly out of scope); the file is
gitignored runtime state like ``data/workspace/``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

# Counts tracked across runs (judge counts only when the judge ran).
DELTA_KEYS = (
    "passed",
    "failed",
    "skipped",
    "total",
    "judge_graded",
    "judge_passed",
    "judge_failed",
)


def summarize_for_history(summary: dict[str, Any]) -> dict[str, Any]:
    """Extract the compact per-run entry stored in the history file."""
    judge = summary.get("judge") or {}
    return {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "passed": int(summary.get("passed") or 0),
        "failed": int(summary.get("failed") or 0),
        "skipped": int(summary.get("skipped") or 0),
        "total": int(summary.get("total") or 0),
        "judge_enabled": bool(judge.get("enabled")),
        "judge_graded": int(judge.get("graded") or 0),
        "judge_passed": int(judge.get("judge_passed") or 0),
        "judge_failed": int(judge.get("judge_failed") or 0),
    }


def compute_delta(
    previous: dict[str, Any] | None, current: dict[str, Any]
) -> dict[str, int] | None:
    """Per-key current-minus-previous delta; None when there is no previous.

    Missing keys on either side count as 0 so the delta is always total.
    """
    if previous is None:
        return None
    return {
        key: int(current.get(key) or 0) - int(previous.get(key) or 0)
        for key in DELTA_KEYS
    }


def format_delta(delta: dict[str, int] | None) -> str:
    """One printable line, e.g. ``passed +2, failed -2`` (zeroes omitted)."""
    if not delta:
        return ""
    parts = [
        f"{key} {value:+d}" for key, value in delta.items() if value != 0
    ]
    return ", ".join(parts)


def last_history_entry(path: Path) -> dict[str, Any] | None:
    """Read the last well-formed JSONL entry; corrupt/missing file → None."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def append_history_entry(path: Path, entry: dict[str, Any]) -> None:
    """Append one entry as a JSONL line (best-effort, never fails the run)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass
