"""Runtime HITL toggle (ADR-016): operator-controlled FreeCAD tool confirmation.

Resolution order (most specific wins):
1. explicit ``build_graph(require_tool_confirm=...)`` — test injection;
2. the runtime override set from the console (``POST /api/tool-confirm``);
3. the ``AGENT_REQUIRE_TOOL_CONFIRM`` setting (default on since ADR-016).

The graph consults this module on every tool-node visit, so flipping the
toggle takes effect immediately — no graph rebuild, mid-session included.
"""

from __future__ import annotations

from companion.config import get_settings

_OVERRIDE: bool | None = None


def get_require_tool_confirm() -> bool:
    if _OVERRIDE is not None:
        return _OVERRIDE
    return get_settings().agent_require_tool_confirm


def require_tool_confirm_source() -> str:
    """Where the effective value came from — "runtime" or "setting"."""
    return "runtime" if _OVERRIDE is not None else "setting"


def set_require_tool_confirm(enabled: bool) -> bool:
    global _OVERRIDE
    _OVERRIDE = bool(enabled)
    return _OVERRIDE


def reset_require_tool_confirm() -> None:
    """Drop the override (tests); the setting default applies again."""
    global _OVERRIDE
    _OVERRIDE = None
