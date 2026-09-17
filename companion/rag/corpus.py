"""Reviewed document selection for the default corpus (ADR-018)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from companion.config import ROOT

MANIFEST = ROOT / "docs" / "corpus_manifest.json"


def manifest_entries(path: Path | None = None) -> list[dict[str, Any]]:
    payload = json.loads((path or MANIFEST).read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("documents"), list):
        raise ValueError("Unsupported corpus manifest")
    entries = payload["documents"]
    seen = set()
    for item in entries:
        required = ("path", "topic", "authority", "reviewed", "version", "applicability")
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip() for k in required):
            raise ValueError("Incomplete corpus document metadata")
        source = item["path"]
        resolved = (ROOT / source).resolve()
        if (not source.startswith("docs/reference/") or ".." in Path(source).parts
                or not resolved.is_relative_to((ROOT / "docs/reference").resolve())
                or resolved.suffix.lower() not in {".md", ".txt"}
                or not resolved.is_file() or source in seen):
            raise ValueError("Invalid or duplicate corpus document")
        seen.add(source)
    return sorted(entries, key=lambda item: item["path"])
