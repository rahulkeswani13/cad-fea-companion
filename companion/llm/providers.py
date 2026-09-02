"""LLM provider interface (Gemini)."""

from __future__ import annotations

import json
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from companion.config import Settings, get_settings


class LLMNotConfiguredError(RuntimeError):
    """Raised when the selected provider has no API key."""


@dataclass
class ToolCallSpec:
    """Provider-agnostic tool call the agent graph can execute."""

    name: str
    args: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"call_{uuid.uuid4().hex[:10]}"


@dataclass
class AgentTurn:
    """One model turn: optional text plus zero or more tool calls."""

    content: str = ""
    tool_calls: list[ToolCallSpec] = field(default_factory=list)
    # H2 token metering: provider usage metadata (input/output/total tokens).
    # None when the provider reports nothing — callers must degrade gracefully.
    usage: dict[str, int] | None = None


def extract_usage(message: Any) -> dict[str, int] | None:
    """Pull ``usage_metadata`` token counts off an LLM response (None if absent)."""
    usage = getattr(message, "usage_metadata", None) or {}
    out: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            out[key] = value
    return out or None


def parse_tools_block(text: str) -> list[ToolCallSpec]:
    """Extract tool calls from a ```tools JSON array ``` block."""
    match = re.search(r"```tools\s*(\[.*?\])\s*```", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    calls: list[ToolCallSpec] = []
    for item in data:
        if isinstance(item, dict) and "name" in item:
            args = item.get("args") or item.get("arguments") or {}
            if not isinstance(args, dict):
                args = {}
            calls.append(ToolCallSpec(name=str(item["name"]), args=args))
    return calls


def _message_text(msg: Any) -> str:
    content = getattr(msg, "content", msg)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content or "")


def _format_messages_for_text_llm(messages: list[Any]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = getattr(msg, "type", None) or msg.__class__.__name__
        name = getattr(msg, "name", None)
        text = _message_text(msg)
        if name:
            lines.append(f"[{role}/{name}]\n{text}")
        else:
            lines.append(f"[{role}]\n{text}")
        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls:
            lines.append(f"(requested tools: {json.dumps(tool_calls)})")
    return "\n\n".join(lines)


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    def complete_messages(
        self,
        messages: list[Any],
        tools: list[Any] | None = None,
    ) -> AgentTurn:
        """Multi-turn completion. Default: flatten to complete() + parse tools block."""
        text = self.complete(
            "You are a helpful assistant. If tools are needed, include a "
            "```tools JSON array ``` block of "
            '[{"name":"...","args":{...}}].',
            _format_messages_for_text_llm(messages)
            + (
                "\n\nAvailable tools:\n"
                + json.dumps(
                    [
                        {"name": getattr(t, "name", str(t)), "description": getattr(t, "description", "")}
                        for t in (tools or [])
                    ],
                    indent=2,
                )
                if tools
                else ""
            ),
        )
        return AgentTurn(content=text, tool_calls=parse_tools_block(text))


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key.strip():
            raise LLMNotConfiguredError(
                "GEMINI_API_KEY is empty. Copy .env.example to .env and set your key."
            )
        self.api_key = api_key.strip()
        self.model = model.strip()

    def _chat(self, tools: list[Any] | None = None):
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=self.model,
            google_api_key=self.api_key,
            temperature=0.2,
        )
        if tools:
            return llm.bind_tools(tools)
        return llm

    def complete(self, system: str, user: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        result = self._chat().invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        return _message_text(result)

    def complete_messages(
        self,
        messages: list[Any],
        tools: list[Any] | None = None,
    ) -> AgentTurn:
        result = self._chat(tools).invoke(messages)
        content = _message_text(result)
        calls: list[ToolCallSpec] = []
        for tc in getattr(result, "tool_calls", None) or []:
            if isinstance(tc, dict):
                calls.append(
                    ToolCallSpec(
                        name=str(tc.get("name", "")),
                        args=dict(tc.get("args") or {}),
                        id=str(tc.get("id") or ""),
                    )
                )
            else:
                calls.append(
                    ToolCallSpec(
                        name=str(getattr(tc, "name", "")),
                        args=dict(getattr(tc, "args", {}) or {}),
                        id=str(getattr(tc, "id", "") or ""),
                    )
                )
        if not calls:
            calls = parse_tools_block(content)
        return AgentTurn(content=content, tool_calls=calls, usage=extract_usage(result))


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    return GeminiProvider(settings.gemini_api_key, settings.gemini_model)


def provider_status(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    return {
        "provider": "gemini",
        "configured": settings.llm_configured(),
        "model": settings.gemini_model,
    }
