"""F06 per-run solve history: append-only JSONL per part + query helpers.

Rules (ADR-006):

- One file per part: ``data/workspace/<part>_runs.jsonl``; one solve = one
  line. Fallback/precomputed solves are recorded too — the ``method`` flag
  distinguishes live CalculiX from demo estimates.
- Append-only; reads are tail-limited (``last_n``). Unbounded growth is
  accepted at demo scale (no rotation, no compaction).
- ``run_id`` = UTC timestamp + short random suffix: sortable and unique.
- History is global per part on disk (shared across chat threads, like the
  design programs); the session keeps only the latest result.
- Reaction forces are NOT captured (deferred to F10 with BC params);
  ``query_results`` states that honestly instead of returning blanks.
- Recording must never fail a successful solve: OSError degrades to a
  ``history_write_error`` warning key (mirrors ``_record_program``).
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from companion.config import get_settings
from companion.tools import design_program as dp

# Compact record: what a run was and what it produced, ordered for reading.
_RECORD_KEYS = (
    "run_id",
    "ts",
    "part",
    "web_type",
    "cell_size_mm",
    "strut_radius_mm",
    "arm_length_mm",
    "length_mm",
    "width_mm",
    "height_mm",
    "program_rev",
    "program_params_hash",
    "force_n",
    "mesh_max_size_mm",
    "method",
    "node_count",
    "fallback",
    "max_von_mises_mpa",
    "max_vm_location_mm",
    "pad_deflection_mm",
    "tip_deflection_mm",
    "mass_kg",
    "relative_density",
    "safety_factor_vs_yield",
    "expected_mpa",
    "expected_ratio",
    "divergence_flag",
    "fcstd_path",
)


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}_{secrets.token_hex(3)}"


def runs_path(part: str) -> Path:
    return get_settings().workspace_dir / f"{part}_runs.jsonl"


def _build_record(
    run_id: str, result: dict[str, Any], geometry: dict[str, Any] | None
) -> dict[str, Any]:
    geo = geometry or {}
    source: dict[str, Any] = {**geo, **result}
    record = {key: source.get(key) for key in _RECORD_KEYS}
    record["run_id"] = run_id
    record["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record["part"] = str(result.get("part") or geo.get("part") or "").strip()
    program = None
    if record["part"] in dp.KNOWN_PARTS:
        try:
            program = dp.load_program(record["part"])
        except OSError:
            program = None
    if program:
        record["program_rev"] = program.get("rev")
        record["program_params_hash"] = program.get("params_hash")
    eva = result.get("expected_vs_actual") or {}
    if isinstance(eva, dict):
        record["expected_mpa"] = eva.get("expected_mpa")
        record["expected_ratio"] = eva.get("ratio")
        record["divergence_flag"] = eva.get("divergence_flag")
    return record


def record_run(result: dict[str, Any], geometry: dict[str, Any] | None) -> str | None:
    """Append one run record for the solve in `result`; stamp run_id on it.

    Returns the run_id, or None when recording degraded (a
    ``history_write_error`` key is set on `result` instead of raising).
    """
    if not isinstance(result, dict) or not result.get("ok"):
        return None
    run_id = result.get("run_id") or new_run_id()
    record = _build_record(run_id, result, geometry)
    if not record.get("part"):
        result["history_write_error"] = "run had no part to record"
        return None
    try:
        path = runs_path(record["part"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
    except OSError as exc:
        result["history_write_error"] = str(exc)
        return None
    result["run_id"] = run_id
    result["runs_path"] = str(path)
    return run_id


def read_runs(part: str, last_n: int = 50) -> list[dict[str, Any]]:
    """Tail of the part's history, oldest -> newest; corrupt lines skipped."""
    try:
        lines = runs_path(part).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    runs: list[dict[str, Any]] = []
    for line in lines[-max(1, int(last_n)):]:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            runs.append(data)
    return runs


def find_run(run_id: str, part: str | None = None) -> dict[str, Any] | None:
    """Newest run with this run_id, searching `part` (or all known parts)."""
    parts = [part] if part else list(dp.KNOWN_PARTS)
    for name in parts:
        for run in reversed(read_runs(name, last_n=500)):
            if run.get("run_id") == run_id:
                return run
    return None
