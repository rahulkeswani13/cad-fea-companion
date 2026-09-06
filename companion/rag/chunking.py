"""Structure-preserving chunks for the evidence-aware RAG index.

The chunker intentionally has no dependency on the store.  This keeps the
formatting and evidence-location rules testable on their own while the store
can continue to deserialize the original three-field ``Chunk`` shape.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """A retrievable span and its source location.

    The first three fields are the legacy constructor contract.  The remaining
    fields are additive and have defaults so existing ``Chunk(id, source,
    text)`` callers and old persisted indexes remain valid.
    """

    chunk_id: str
    source: str
    text: str
    section_id: str = ""
    heading: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


_ATX_HEADING = re.compile(r"^\s{0,3}(#{1,6})(?:\s+|$)(.*?)\s*$")
_SETEXT_UNDERLINE = re.compile(r"^\s*(=+|-+)\s*$")
_TABLE_SEPARATOR = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
_SCOPE_MARKERS = re.compile(
    r"\b(?:scope\s+caveat|applies\s+to|applicability|not\s+verified|teaching\s+values|not\s+design\s+allowables)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Block:
    kind: str
    lines: tuple[str, ...]
    start_line: int
    end_line: int


@dataclass
class _Section:
    section_id: str
    heading: str | None
    heading_line: str | None
    heading_number: int | None
    start_line: int = 1
    end_line: int = 1
    blocks: list[_Block] = field(default_factory=list)


def _slug(value: str) -> str:
    """Return a stable, readable slug without making an empty identity."""

    normalized = unicodedata.normalize("NFKC", value).lower()
    slug = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-")
    return slug or "section"


def _heading_value(line: str) -> str | None:
    match = _ATX_HEADING.match(line)
    if not match:
        return None
    # Closing ATX hashes are presentation syntax, not part of the heading.
    return re.sub(r"\s+#+\s*$", "", match.group(2)).strip() or "section"


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and bool(stripped)


def _is_table_start(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and _is_table_row(lines[index])
        and bool(_TABLE_SEPARATOR.match(lines[index + 1]))
    )


def _paragraph_caveats(lines: list[str]) -> list[tuple[str, int, int, bool]]:
    """Collect only explicit caveats present in the source document.

    Caveats retain metadata and are repeated only within their scope. The marker requirement
    is deliberately conservative: a generic sentence about assumptions is not
    promoted into a document-wide caveat unless the source names its scope or
    verification status.
    """

    caveats: list[tuple[str, int, int, bool]] = []
    index = 0
    seen_subsection = False
    while index < len(lines):
        atx_heading = _ATX_HEADING.match(lines[index])
        if atx_heading:
            if len(atx_heading.group(1)) >= 2:
                seen_subsection = True
            index += 1
            continue
        if not lines[index].strip():
            index += 1
            continue
        if _heading_value(lines[index]) is not None:
            index += 1
            continue
        start = index
        while index + 1 < len(lines) and lines[index + 1].strip():
            if _heading_value(lines[index + 1]) is not None:
                break
            index += 1
        paragraph = "\n".join(lines[start : index + 1]).strip()
        if _SCOPE_MARKERS.search(paragraph) and not any(
            paragraph == existing[0] for existing in caveats
        ):
            explicit_scope = bool(re.search(r"\bscope\s+caveat\b", paragraph, re.IGNORECASE))
            caveats.append((paragraph, start + 1, index + 1, explicit_scope or not seen_subsection))
        index += 1
    return caveats


def _parse_sections(lines: list[str], source: str) -> list[_Section]:
    sections: list[_Section] = []
    slug_counts: dict[str, int] = {}
    current: _Section | None = None
    index = 0

    def start_section(
        heading: str | None, heading_line: str | None, heading_number: int | None
    ) -> _Section:
        if sections:
            sections[-1].end_line = (heading_number or 1) - 1
        slug = _slug(heading or "document")
        slug_counts[slug] = slug_counts.get(slug, 0) + 1
        suffix = "" if slug_counts[slug] == 1 else f"-{slug_counts[slug]}"
        section = _Section(
            section_id=f"{source}::{slug}{suffix}",
            heading=heading,
            heading_line=heading_line,
            heading_number=heading_number,
            start_line=heading_number or 1,
        )
        sections.append(section)
        return section

    current = start_section(None, None, None)
    while index < len(lines):
        heading = _heading_value(lines[index])
        atx = _ATX_HEADING.match(lines[index])
        if heading is not None and atx:
            current = start_section(heading, lines[index], index + 1)
            index += 1
            continue

        # Setext headings are common in hand-written reference notes.  Treat
        # the title and underline as the section heading, preserving both lines
        # in the rendered chunk and their source span.
        if (
            index + 1 < len(lines)
            and lines[index].strip()
            and _SETEXT_UNDERLINE.match(lines[index + 1])
        ):
            current = start_section(lines[index].strip(), lines[index], index + 1)
            current.heading_number = index + 1
            # Store the underline as part of the heading line text below.
            current.heading_line = f"{lines[index]}\n{lines[index + 1]}"
            index += 2
            continue

        if not lines[index].strip():
            index += 1
            continue

        if _is_table_start(lines, index):
            start = index
            index += 2
            while index < len(lines) and lines[index].strip() and _is_table_row(lines[index]):
                index += 1
            current.blocks.append(
                _Block("table", tuple(lines[start:index]), start + 1, index)
            )
            continue

        start = index
        index += 1
        while index < len(lines) and lines[index].strip():
            if _heading_value(lines[index]) is not None or _is_table_start(lines, index):
                break
            # A setext underline terminates the preceding paragraph and starts
            # a new section on the next loop iteration.
            if index + 1 < len(lines) and _SETEXT_UNDERLINE.match(lines[index + 1]):
                break
            index += 1
        current.blocks.append(
            _Block("paragraph", tuple(lines[start:index]), start + 1, index)
        )

    if sections:
        sections[-1].end_line = len(lines)
    # A leading document section with no content is only a parser sentinel.
    return [section for section in sections if section.blocks or section.heading is not None]


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """Split at sentence/word boundaries while preserving every character."""

    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        limit = min(start + max_chars, len(text))
        if limit == len(text):
            pieces.append(text[start:])
            break

        # Prefer a sentence boundary, then the last whitespace boundary.  The
        # delimiter stays with the left piece, so concatenating pieces exactly
        # reconstructs the source paragraph.
        sentence = list(re.finditer(r"[.!?](?=\s|$)", text[start:limit]))
        boundary = start + sentence[-1].end() if sentence else None
        if boundary is None or boundary <= start:
            whitespace = [match.start() + 1 for match in re.finditer(r"\s", text[start:limit])]
            boundary = start + whitespace[-1] if whitespace else limit
        pieces.append(text[start:boundary])
        start = boundary
    return pieces


def _chunk_text_id(section_id: str, text: str, seen: dict[str, int]) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    base = f"{section_id}::{digest}"
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}-{seen[base]}"


def chunk_text(text: str, source: str, max_chars: int = 800) -> list[Chunk]:
    """Chunk Markdown while retaining section, table, and line evidence.

    ``max_chars`` is a target for normal prose.  A heading or table row that
    cannot be divided without changing its meaning may exceed it; rows are
    never silently cut in half.
    """

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not text or not text.strip():
        return []

    lines = text.splitlines()
    caveats = _paragraph_caveats(lines)
    sections = _parse_sections(lines, source)
    chunks: list[Chunk] = []
    seen_ids: dict[str, int] = {}

    def emit(
        section: _Section,
        value: str,
        start_line: int,
        end_line: int,
        block_type: str,
    ) -> None:
        if not value:
            return
        applicable_caveats = [
            record
            for record in caveats
            if record[3]
            or section.start_line <= record[1] <= section.end_line
        ]
        repeated_caveats = [caveat for caveat, _, _, _ in applicable_caveats if caveat not in value]
        if repeated_caveats:
            caveat_text = "\n\n".join(repeated_caveats)
            if section.heading_line and value.startswith(section.heading_line):
                value = (
                    f"{section.heading_line}\n\n{caveat_text}\n\n"
                    f"{value[len(section.heading_line) + 2 :]}"
                ).rstrip("\n")
            else:
                value = f"{caveat_text}\n\n{value}".rstrip("\n")
            caveat_starts = [
                start for caveat, start, _, _ in applicable_caveats if caveat in repeated_caveats
            ]
            caveat_ends = [
                end for caveat, _, end, _ in applicable_caveats if caveat in repeated_caveats
            ]
            start_line = min([start_line, *caveat_starts])
            end_line = max([end_line, *caveat_ends])

        metadata: dict[str, Any] = {"block_type": block_type}
        if applicable_caveats:
            metadata["scope_caveats"] = [caveat for caveat, _, _, _ in applicable_caveats]
            metadata["scope_caveat_ranges"] = [
                {"start_line": start, "end_line": end}
                for _, start, end, _ in applicable_caveats
            ]
            if repeated_caveats:
                metadata["scope_caveats_repeated"] = True
        chunks.append(
            Chunk(
                chunk_id=_chunk_text_id(section.section_id, value, seen_ids),
                source=source,
                text=value,
                section_id=section.section_id,
                heading=section.heading,
                start_line=start_line,
                end_line=end_line,
                metadata=metadata,
            )
        )

    for section in sections:
        prefix = section.heading_line or ""
        if prefix:
            prefix += "\n\n"
        current = prefix
        current_start = section.heading_number or None
        current_end = section.heading_number or None
        current_type = "heading"

        def flush(force_heading: bool = False) -> None:
            nonlocal current, current_start, current_end, current_type
            if current.strip() and (current_type != "heading" or force_heading):
                emit(
                    section,
                    current.rstrip("\n"),
                    current_start or 1,
                    current_end or current_start or 1,
                    current_type,
                )
            current = prefix
            current_start = section.heading_number or None
            current_end = section.heading_number or None
            current_type = "heading"

        for block in section.blocks:
            if block.kind == "table":
                flush()
                header = "\n".join(block.lines[:2])
                rows = list(block.lines[2:])
                table_prefix = prefix + header
                table_current = table_prefix
                table_start = section.heading_number or block.start_line
                table_end = block.start_line + 1
                if not rows:
                    emit(section, table_current, table_start, table_end, "table")
                    continue
                for row_offset, row in enumerate(rows, start=2):
                    candidate = f"{table_current}\n{row}"
                    # Always attach the first row to the header.  A header-only
                    # chunk loses the row's meaning, and an indivisible row is
                    # allowed to exceed the prose target.
                    if len(candidate) <= max_chars or table_current == table_prefix:
                        table_current = candidate
                        table_end = block.start_line + row_offset
                    else:
                        emit(section, table_current, table_start, table_end, "table")
                        table_current = f"{table_prefix}\n{row}"
                        table_start = section.heading_number or block.start_line
                        table_end = block.start_line + row_offset
                emit(section, table_current, table_start, table_end, "table")
                continue

            paragraph = "\n".join(block.lines)
            separator = "" if current == prefix else "\n\n"
            # Keep an explicit document-scope caveat whole.  Splitting the
            # warning itself would make every continuation look like a new,
            # potentially fabricated caveat when it is repeated below.
            if any(paragraph.strip() == caveat.strip() for caveat, _, _, _ in caveats):
                flush()
                emit(
                    section,
                    f"{prefix}{paragraph}".rstrip("\n"),
                    section.heading_number or block.start_line,
                    block.end_line,
                    "paragraph",
                )
                current = prefix
                current_start = section.heading_number or None
                current_end = section.heading_number or None
                current_type = "heading"
                continue
            if len(current) + len(separator) + len(paragraph) <= max_chars:
                current = f"{current}{separator}{paragraph}"
                current_start = current_start or block.start_line
                current_end = block.end_line
                current_type = "paragraph"
                continue

            flush()
            body_budget = max_chars - len(prefix)
            if body_budget <= 0:
                # An indivisible heading consumes the target; retain it as its
                # own evidence span, then chunk the prose independently.
                if prefix:
                    flush()
                body_budget = max_chars
                body_prefix = ""
            else:
                body_prefix = prefix
            pieces = _split_long_text(paragraph, body_budget)
            for piece_index, piece in enumerate(pieces):
                piece_start = block.start_line
                piece_end = block.end_line
                emit(
                    section,
                    f"{body_prefix}{piece}".rstrip("\n"),
                    piece_start if not body_prefix else section.heading_number or piece_start,
                    piece_end,
                    "paragraph",
                )
            current = prefix
            current_start = section.heading_number or None
            current_end = section.heading_number or None
            current_type = "heading"

        flush(force_heading=not section.blocks)

    return chunks


__all__ = ["Chunk", "chunk_text"]
