"""F02 tool outcome envelopes.

Every tool result that reaches the LLM flows through `wrap_tool_call` /
`envelope` so that:

- successes stay compact and carry a receipt (tool, elapsed_s, what changed);
- failures carry exactly one error line, an `error_class`, and one concrete
  `correction` — never a raw traceback or stdout/stderr tails;
- raw diagnostics are preserved on disk (debug log) and referenced by
  `debug_ref` instead of being serialized into chat context.

The envelope is flat-additive: existing result keys keep working; we only add
`receipt` (always), and on failure `error_class` + `correction` (+ `debug_ref`
when raw output was moved to the log). Units stay encoded in key names
(`_mm`, `_n`, `_mpa`) per repo convention; the receipt does not duplicate KPIs.
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from companion.config import get_settings

# One concrete correction per failure class. F13 (repair loop) extends this
# table with a fuller failure-class table and doc-grounded hints.
CORRECTIONS: dict[str, str] = {
    "bad_params": "Fix the reported parameter value and retry the same tool.",
    "unknown_tool": (
        "Call one of the tools listed in the system prompt (TOOL_SPECS), "
        "e.g. create_brake_pedal or apply_load_and_solve."
    ),
    "no_geometry": (
        "Call create_brake_pedal or create_cantilever "
        "first, then retry."
    ),
    "no_results": "Call apply_load_and_solve first, then retry the query.",
    "freecad_missing": (
        "Install FreeCAD (or point FREECAD_CMD at FreeCADCmd) and retry; "
        "the analytical fallback result is still usable."
    ),
    "freecad_timeout": (
        "Retry with a coarser mesh_max_size_mm, or accept the analytical "
        "fallback result."
    ),
    "freecad_crash": (
        "Retry once with default parameters; if it repeats, use the "
        "analytical fallback and inspect data/workspace/logs/tool_debug.log."
    ),
    "mesh_failed": "Retry with strut_radius_mm >= 2.2 and a coarser mesh_max_size_mm.",
    "solve_failed": (
        "Retry once with default parameters; if it repeats, use the "
        "analytical fallback result."
    ),
    "geometry_invalid": (
        "Retry with lattice-friendly parameters (xtruss strut ~2.5 mm, "
        "fcc/bcc strut radius >= 2.2 mm, cell_size 12-20 mm); see "
        "validation.checks and data/workspace/logs/tool_debug.log."
    ),
    "internal_error": (
        "Retry the tool once; if it repeats, check "
        "data/workspace/logs/tool_debug.log."
    ),
    "user_cancelled": "Re-run the request and approve the FreeCAD confirmation prompt.",
    "unsupported_setup": (
        "Switch to a live-solve setup (web_type xtruss or solid with FreeCAD "
        "available), then re-run the convergence study."
    ),
}

# Ordered: first matching rule wins (specific beats generic).
_CLASSIFIERS: list[tuple[tuple[str, ...], str]] = [
    (("unknown tool",), "unknown_tool"),
    (
        ("must be one of", "invalid parameter", "missing "),
        "bad_params",
    ),
    (("no geometry", "no lattice geometry", "no freecad document"), "no_geometry"),
    (("no results yet",), "no_results"),
    (
        ("freecadcmd not found", "freecad not installed", "freecad gui not found"),
        "freecad_missing",
    ),
    (("timed out",), "freecad_timeout"),
    # F03 gate messages must classify before the generic traceback/crash rule.
    (
        ("geometry validation failed", "isvalid() returned false"),
        "geometry_invalid",
    ),
    (("no companion_json", "qt aborted", "traceback"), "freecad_crash"),
    (("mesh", "gmsh"), "mesh_failed"),
    (("calculix", "solve fail", "von mises results"), "solve_failed"),
]

_RAW_KEYS = ("stdout_tail", "stderr_tail")
_ERROR_KEYS = ("error", "freecad_error")
_MAX_ERROR_CHARS = 300


def classify_error(text: str) -> str:
    """Map a raw error string to a failure class (default internal_error)."""
    lower = (text or "").lower()
    for needles, cls in _CLASSIFIERS:
        if any(n in lower for n in needles):
            return cls
    return "internal_error"


def correction_for(error_class: str, override: str | None = None) -> str:
    if override and override.strip():
        return override.strip()
    return CORRECTIONS.get(error_class, CORRECTIONS["internal_error"])


def _condense_error(text: str) -> str:
    """Collapse a traceback/long error into one actionable line."""
    text = (text or "").strip()
    if "Traceback (most recent call last)" in text:
        lines = [line for line in text.splitlines() if line.strip()]
        if lines:
            text = lines[-1].strip()
    if len(text) > _MAX_ERROR_CHARS:
        text = text[:_MAX_ERROR_CHARS].rsplit(" ", 1)[0] + "…"
    return text


# Public alias: F08's convergence study condenses sub-run errors the same way.
condense_error = _condense_error


def write_debug(tool: str, blob: str) -> str | None:
    """Append raw diagnostics to the workspace debug log; return its path."""
    try:
        settings = get_settings()
        settings.ensure_dirs()
        log_dir = settings.workspace_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path: Path = log_dir / "tool_debug.log"
        stamp = datetime.now().isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n=== {stamp} · {tool} ===\n{blob}\n")
        return str(path)
    except OSError:
        return None


def envelope(
    result: dict[str, Any],
    *,
    tool: str,
    elapsed_s: float,
    changed: list[str] | None = None,
) -> dict[str, Any]:
    """Return `result` as a flat-additive outcome envelope.

    Moves raw diagnostics (stdout/stderr tails, tracebacks, oversized errors)
    to the debug log and adds `debug_ref`; classifies failures and guarantees
    `error_class` + one `correction`; always attaches a receipt.
    """
    out = dict(result or {})
    raw: dict[str, Any] = {}
    for key in _RAW_KEYS:
        if key in out:
            raw[key] = out.pop(key)
    for key in _ERROR_KEYS:
        value = out.get(key)
        if isinstance(value, str) and (
            "Traceback" in value or len(value) > _MAX_ERROR_CHARS
        ):
            raw[f"raw_{key}"] = value
            out[key] = _condense_error(value)
    if raw:
        ref = write_debug(tool, json.dumps(raw, indent=2, default=str))
        if ref:
            out["debug_ref"] = ref

    if not out.get("ok"):
        error_text = out.get("error")
        if not isinstance(error_text, str) or not error_text.strip():
            error_text = f"{tool} failed"
            out["error"] = error_text
        error_class = str(out.get("error_class") or classify_error(error_text))
        out["error_class"] = error_class
        out["correction"] = correction_for(
            error_class, out.get("correction") if isinstance(out.get("correction"), str) else None
        )

    out["receipt"] = {
        "tool": tool,
        "elapsed_s": round(float(elapsed_s), 3),
        "changed": list(changed or []),
    }
    return out


def wrap_tool_call(
    name: str,
    args: dict[str, Any],
    fn: Callable[[str, dict[str, Any]], dict[str, Any]],
    *,
    state_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Invoke a tool and envelope its result (F02 choke point).

    `state_fn` (e.g. cad_fea.get_state) enables changed-detection: the receipt
    records whether the call replaced session geometry/results. Unexpected
    exceptions become internal_error failures instead of graph crashes.
    """
    before = dict(state_fn()) if state_fn else {}
    start = time.perf_counter()
    try:
        result = fn(name, args)
    except Exception as exc:  # noqa: BLE001 — tools must not crash the graph
        result = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "error_class": "internal_error",
            "debug_ref": write_debug(name, traceback.format_exc()),
        }
    elapsed_s = time.perf_counter() - start
    after = state_fn() if state_fn else {}
    changed: list[str] = []
    if before.get("geometry") is not after.get("geometry") and after.get(
        "geometry"
    ) is not None:
        changed.append("geometry_replaced")
    if before.get("results") is not after.get("results") and after.get(
        "results"
    ) is not None:
        changed.append("results_replaced")
    return envelope(result, tool=name, elapsed_s=elapsed_s, changed=changed)
