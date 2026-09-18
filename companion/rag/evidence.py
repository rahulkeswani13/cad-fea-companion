"""Bounded, inspectable evidence checks for generated RAG answers (ADR-020)."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

SUPPORT_STATES = (
    "supported",
    "partially_supported",
    "insufficient",
    "check_unavailable",
)
ACTIONS = ("answer", "clarify", "refuse", "abstain")

_FOLLOWUP = re.compile(
    r"^(?:and\b|also\b|but\b|then\b|what about\b|how about\b|why\b|"
    r"what does that\b|does (?:it|that|this)\b|is (?:it|that|this)\b)|"
    r"\b(?:it|that|this|those|these|same|previous|above)\b",
    re.IGNORECASE,
)
_EVIDENCE_BLOCK = re.compile(
    r"```(?:evidence-json|json)\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL
)
_NUMBER = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_MARKDOWN_RULE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")
_ABBREVIATIONS = (
    "e.g.", "i.e.", "vs.", "approx.", "fig.", "dr.", "mr.", "mrs.",
    "ms.", "prof.", "etc.", "no.",
)


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _split_sentences(paragraph: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    for boundary in _SENTENCE_BOUNDARY.finditer(paragraph):
        candidate = paragraph[start:boundary.start()].strip()
        if candidate.casefold().endswith(_ABBREVIATIONS):
            continue
        if candidate:
            sentences.append(candidate)
        start = boundary.end()
    tail = paragraph[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _document_segments(content: str) -> list[tuple[str, str]]:
    """Split one retrieved chunk without changing the stored corpus or index."""
    lines = content.splitlines()
    segments: list[tuple[str, str]] = []
    prose: list[str] = []

    def flush_prose() -> None:
        if not prose:
            return
        paragraph = " ".join(line.strip() for line in prose if line.strip()).strip()
        prose.clear()
        if not paragraph:
            return
        for sentence in _split_sentences(paragraph):
            if sentence.strip():
                segments.append(("sentence", sentence.strip()))

    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            flush_prose()
            index += 1
            continue
        if _is_table_row(line):
            flush_prose()
            table: list[str] = []
            while index < len(lines) and _is_table_row(lines[index]):
                table.append(lines[index].strip())
                index += 1
            meaningful = [row for row in table if not _MARKDOWN_RULE.match(row)]
            if not meaningful:
                continue
            header = meaningful[0]
            rows = meaningful[1:] or [header]
            for row in rows:
                text = row if row == header else f"{header}\n{row}"
                segments.append(("table_row", text))
            continue
        stripped = line.strip()
        if stripped.startswith(("#", "- ", "* ", "> ")):
            flush_prose()
            segments.append(("sentence", stripped))
        else:
            prose.append(line)
        index += 1
    flush_prose()
    if not segments and content.strip():
        segments.append(("content", content.strip()))
    return segments


def _structured_segments(value: Any, path: str = "$") -> list[tuple[str, str]]:
    if isinstance(value, dict):
        rows: list[tuple[str, str]] = []
        for key in sorted(value, key=str):
            rows.extend(_structured_segments(value[key], f"{path}.{key}"))
        return rows
    if isinstance(value, list):
        rows = []
        for index, item in enumerate(value):
            rows.extend(_structured_segments(item, f"{path}[{index}]"))
        return rows
    return [("field", f"{path} = {json.dumps(value, default=str, sort_keys=True)}")]


def _with_spans(
    item: dict[str, Any],
    *,
    structured_value: Any | None = None,
) -> dict[str, Any]:
    if structured_value is not None:
        pieces = _structured_segments(structured_value)
    else:
        pieces = _document_segments(str(item.get("content") or ""))
    if structured_value is not None:
        bounded: list[tuple[str, str]] = []
        remaining = 2000
        for kind, text in pieces:
            if remaining <= 0:
                break
            clipped = text[:remaining]
            if clipped:
                bounded.append((kind, clipped))
                remaining -= len(clipped)
        pieces = bounded
    item["spans"] = [
        {
            "span_id": f"{item['evidence_id']}:S{index}",
            "evidence_id": item["evidence_id"],
            "source": item.get("source"),
            "text": text,
            "kind": kind,
        }
        for index, (kind, text) in enumerate(pieces, 1)
    ]
    return item


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, list):
        return "\n".join(
            str(block.get("text", "")) if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content or "")


def resolve_retrieval_query(
    question: str,
    messages: list[BaseMessage] | None = None,
    cad_geometry: dict[str, Any] | None = None,
    cad_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve an elliptical follow-up from one prior user turn and CAD state."""
    current = question.strip()
    humans = [
        _message_text(message).strip()
        for message in (messages or [])
        if isinstance(message, HumanMessage) and _message_text(message).strip()
    ]
    previous = next((item for item in reversed(humans) if item != current), None)
    followup = bool(previous and (_FOLLOWUP.search(current) or len(current.split()) <= 5))
    parts = [current]
    if followup and previous:
        parts.append(f"Previous user question: {previous}")

    cad = cad_results or cad_geometry or {}
    cad_terms = []
    for key in ("part", "web_type", "material", "material_id"):
        value = cad.get(key)
        if value is not None:
            cad_terms.append(f"{key}={value}")
    if cad_terms:
        parts.append("Current CAD state: " + ", ".join(cad_terms))
    return {
        "query": "\n".join(part for part in parts if part),
        "followup_resolved": followup,
        "previous_user_question": previous if followup else None,
        "cad_context_used": bool(cad_terms),
    }


def evidence_catalog(
    citations: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    *,
    question: str = "",
    cad_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Create stable per-answer evidence IDs without changing source identity."""
    catalog: list[dict[str, Any]] = []
    if question.strip():
        catalog.append(_with_spans({
            "evidence_id": "Q1",
            "kind": "user_question",
            "source": "current user message",
            "section_id": None,
            "chunk_id": None,
            "authority": "user-stated premise only",
            "applicability": "supports what the user asked or supplied, not its truth",
            "conditions": [],
            "content": question.strip(),
        }))
    if cad_state:
        catalog.append(_with_spans({
            "evidence_id": "C1",
            "kind": "cad_state",
            "source": "current session CAD state",
            "section_id": None,
            "chunk_id": None,
            "authority": "current in-process session state",
            "applicability": "current thread only; method and verification limits apply",
            "conditions": [],
            "content": json.dumps(cad_state, default=str, sort_keys=True)[:2000],
        }, structured_value=cad_state))
    for index, hit in enumerate(citations[:4], 1):
        metadata = hit.get("metadata") or {}
        catalog.append(_with_spans({
            "evidence_id": f"D{index}",
            "kind": "document",
            "source": hit.get("source"),
            "section_id": hit.get("section_id"),
            "chunk_id": hit.get("chunk_id"),
            "authority": metadata.get("authority"),
            "applicability": metadata.get("applicability"),
            "conditions": metadata.get("scope_caveats") or [],
            "content": str(hit.get("text") or ""),
        }))
    for index, item in enumerate(tool_results[-6:], 1):
        result = item.get("result") or {}
        catalog.append(_with_spans({
            "evidence_id": f"T{index}",
            "kind": "tool_result",
            "source": item.get("name"),
            "section_id": None,
            "chunk_id": None,
            "authority": "current session tool result",
            "applicability": "recorded inputs, method, mesh, and verification scope",
            "conditions": [],
            "content": json.dumps(result, default=str, sort_keys=True)[:2000],
            "ok": result.get("ok") is True,
        }, structured_value=result))
    return catalog


def format_evidence_for_prompt(catalog: list[dict[str, Any]]) -> str:
    lines = []
    for item in catalog:
        spans = item.get("spans") or []
        span_text = "\n".join(
            f"[{span.get('span_id')}] {span.get('text') or ''}" for span in spans
        )
        lines.append(
            f"[{item['evidence_id']}] {item.get('kind')} {item.get('source')} "
            f"section={item.get('section_id') or 'n/a'}; "
            f"authority={item.get('authority') or 'unspecified'}; "
            f"applicability={item.get('applicability') or 'unspecified'}; "
            f"conditions={json.dumps(item.get('conditions') or [])}\n"
            f"{span_text or item.get('content') or ''}"
        )
    return "\n\n".join(lines) or "(none)"


def _parse_payload(draft: str) -> dict[str, Any] | None:
    match = _EVIDENCE_BLOCK.search(draft)
    raw = match.group(1) if match else draft.strip()
    if not raw.startswith("{"):
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _numbers(text: str) -> list[float]:
    values = []
    for token in _NUMBER.findall(text):
        try:
            values.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return values


def _number_supported(number: float, evidence_text: str) -> bool:
    return any(
        abs(number - candidate) <= max(1e-9, abs(number) * 1e-6)
        for candidate in _numbers(evidence_text)
    )


def unavailable_assessment(answer: str, reason: str) -> dict[str, Any]:
    return {
        "status": "check_unavailable",
        "action": "answer",
        "checked": False,
        "structural_check": "unavailable",
        "semantic_check": "not_performed",
        "repair_attempted": False,
        "claims": [],
        "gaps": [reason],
        "answer": answer.strip(),
    }


def _format_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold().translate(
        str.maketrans({"≤": "<=", "≥": ">=", "≠": "!=", "−": "-", "＋": "+"})
    )
    return re.findall(
        r"(?:<=|>=|==|!=|[<>±≈≃≅~=+\-])|[^\W_]+(?:[.,]\d+)?",
        normalized,
        flags=re.UNICODE,
    )


def _normalized_contains(needle: str, haystack: str) -> bool:
    wanted = _format_tokens(needle)
    available = _format_tokens(haystack)
    if not wanted or len(wanted) > len(available):
        return False
    width = len(wanted)
    return any(
        available[index:index + width] == wanted
        for index in range(len(available) - width + 1)
    )


def _resolved_spans(
    item: dict[str, Any],
    quote: str,
    method: str,
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for span in item.get("spans") or []:
        text = str(span.get("text") or "")
        matched = quote in text if method == "exact_quote" else _normalized_contains(quote, text)
        if matched:
            resolved.append({
                "span_id": span.get("span_id"),
                "evidence_id": span.get("evidence_id"),
                "source": span.get("source"),
                "text": text,
                "kind": span.get("kind"),
                "provenance_method": method,
            })
    if resolved:
        return resolved

    content = str(item.get("content") or "")
    if method == "exact_quote":
        quote_start = content.find(quote)
        quote_end = quote_start + len(quote)
        if quote_start >= 0:
            for span in item.get("spans") or []:
                text = str(span.get("text") or "")
                span_start = content.find(text)
                span_end = span_start + len(text)
                if span_start >= 0 and max(quote_start, span_start) < min(quote_end, span_end):
                    resolved.append({
                        "span_id": span.get("span_id"),
                        "evidence_id": span.get("evidence_id"),
                        "source": span.get("source"),
                        "text": text,
                        "kind": span.get("kind"),
                        "provenance_method": method,
                    })
    else:
        for span in item.get("spans") or []:
            text = str(span.get("text") or "")
            if text and _normalized_contains(text, quote):
                resolved.append({
                    "span_id": span.get("span_id"),
                    "evidence_id": span.get("evidence_id"),
                    "source": span.get("source"),
                    "text": text,
                    "kind": span.get("kind"),
                    "provenance_method": method,
                })
    if resolved:
        return resolved
    return [{
        "span_id": f"{item['evidence_id']}:LEGACY",
        "evidence_id": item["evidence_id"],
        "source": item.get("source"),
        "text": content,
        "kind": "legacy_parent",
        "provenance_method": method,
    }]


def _quote_issues(
    raw_quotes: Any,
    cited: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], str | None]:
    if not isinstance(raw_quotes, list) or not raw_quotes:
        return ["no supporting quotes or evidence spans"], [], None
    cited_by_id = {item["evidence_id"]: item for item in cited}
    issues: list[str] = []
    covered: set[str] = set()
    resolved: list[dict[str, Any]] = []
    methods: set[str] = set()
    for raw_quote in raw_quotes:
        if not isinstance(raw_quote, dict):
            issues.append("malformed supporting quote")
            continue
        evidence_id = str(raw_quote.get("evidence_id") or "")
        quote = str(raw_quote.get("quote") or "").strip()
        item = cited_by_id.get(evidence_id)
        if item is None:
            issues.append(f"supporting quote uses uncited evidence ID: {evidence_id or '(empty)'}")
        elif len(quote) < 12 or len(re.findall(r"\w+", quote)) < 3:
            issues.append(f"supporting quote is too short for {evidence_id}")
        else:
            content = str(item.get("content") or "")
            if quote in content:
                method = "exact_quote"
            elif _normalized_contains(quote, content):
                method = "normalized_quote"
            else:
                issues.append(
                    f"supporting quote does not match source formatting for {evidence_id}"
                )
                continue
            covered.add(evidence_id)
            methods.add(method)
            for match in _resolved_spans(item, quote, method):
                if match["span_id"] not in {span["span_id"] for span in resolved}:
                    resolved.append(match)
    required = {
        item["evidence_id"] for item in cited
        if item.get("kind") in {"document", "cad_state", "tool_result"}
    }
    missing = sorted(required - covered)
    if missing:
        issues.append("missing supporting provenance for: " + ", ".join(missing))
    method = None
    if "normalized_quote" in methods:
        method = "normalized_quote"
    elif "exact_quote" in methods:
        method = "exact_quote"
    return issues, resolved, method


def _finalize_assessment(
    action: str,
    checked_claims: list[dict[str, Any]],
    declared_gaps: list[str],
    fallback_answer: str,
) -> dict[str, Any]:
    supported = [
        claim for claim in checked_claims
        if claim["structurally_supported"] and claim["text"]
    ]
    unsupported = [claim for claim in checked_claims if not claim["structurally_supported"]]
    gaps = list(declared_gaps)
    gaps.extend(issue for claim in unsupported for issue in claim["issues"])
    gaps = list(dict.fromkeys(gaps))
    if action in {"clarify", "refuse", "abstain"} and not checked_claims:
        status = "insufficient"
    elif checked_claims and not unsupported and not gaps:
        status = "supported"
    elif supported:
        status = "partially_supported"
    else:
        status = "insufficient"

    if supported:
        answer = "\n\n".join(claim["text"] for claim in supported)
    elif action == "clarify":
        answer = fallback_answer or "Please clarify the missing engineering context."
    elif action in {"refuse", "abstain"}:
        answer = fallback_answer or "I cannot provide that claim from the available evidence."
    else:
        answer = "I do not have enough supported evidence to answer that."
    if gaps:
        answer += "\n\nEvidence gaps: " + "; ".join(gaps)
    return {
        "status": status,
        "action": action,
        "checked": True,
        "structural_check": "passed" if not unsupported else "failed",
        "semantic_check": "pending_manual_or_judge",
        "repair_attempted": False,
        "claims": checked_claims,
        "gaps": gaps,
        "answer": answer,
    }


def assess_structured_draft(
    draft: str,
    catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bound spans, tool success, exact numbers, and legacy quote provenance.

    This deliberately does not claim semantic entailment. That separate result
    remains pending until the answer judge and human reviewer assess it.
    """
    payload = _parse_payload(draft)
    if payload is None:
        return unavailable_assessment(draft, "structured evidence draft missing or invalid")

    action = str(payload.get("action") or "answer")
    if action not in ACTIONS:
        action = "answer"
    raw_claims = payload.get("claims")
    if not isinstance(raw_claims, list):
        return unavailable_assessment(str(payload.get("answer") or draft), "claims list missing")

    by_id = {item["evidence_id"]: item for item in catalog}
    span_by_id = {
        span["span_id"]: (item, span)
        for item in catalog
        for span in item.get("spans") or []
    }
    checked_claims = []
    for raw_claim in raw_claims:
        if not isinstance(raw_claim, dict):
            continue
        text = str(raw_claim.get("text") or "").strip()
        evidence_ids = raw_claim.get("evidence_ids") or []
        if not isinstance(evidence_ids, list):
            evidence_ids = []
        evidence_ids = [str(value) for value in evidence_ids]
        span_ids = raw_claim.get("evidence_span_ids") or []
        if not isinstance(span_ids, list):
            span_ids = []
        span_ids = [str(value) for value in span_ids]
        issues = []
        if not text:
            issues.append("empty claim")
        invalid_spans = [value for value in span_ids if value not in span_by_id]
        if invalid_spans:
            issues.append("unknown evidence span IDs: " + ", ".join(invalid_spans))
        valid_span_pairs = [span_by_id[value] for value in span_ids if value in span_by_id]
        span_parent_ids = list(dict.fromkeys(
            str(span.get("evidence_id")) for _, span in valid_span_pairs
        ))
        if not evidence_ids and span_parent_ids:
            evidence_ids = span_parent_ids
        if not evidence_ids and not span_ids:
            issues.append("no evidence IDs")
        invalid = [value for value in evidence_ids if value not in by_id]
        if invalid:
            issues.append("unknown evidence IDs: " + ", ".join(invalid))
        uncited_span_parents = [value for value in span_parent_ids if value not in evidence_ids]
        if uncited_span_parents:
            issues.append(
                "evidence spans use uncited evidence IDs: " + ", ".join(uncited_span_parents)
            )
        cited = [by_id[value] for value in evidence_ids if value in by_id]
        if cited and all(item.get("kind") == "user_question" for item in cited):
            issues.append("user question cannot establish a factual claim")
        failed_tools = [
            item["evidence_id"] for item in cited
            if item["kind"] == "tool_result" and not item.get("ok")
        ]
        if failed_tools:
            issues.append(
                "failed tool result cited as factual support: " + ", ".join(failed_tools)
            )
        resolved_spans: list[dict[str, Any]] = []
        provenance_method: str | None = None
        if span_ids:
            covered = set(span_parent_ids)
            missing_span_parents = sorted(
                item["evidence_id"] for item in cited
                if item.get("kind") in {"document", "cad_state", "tool_result"}
                and item["evidence_id"] not in covered
            )
            if missing_span_parents:
                issues.append("missing evidence span for: " + ", ".join(missing_span_parents))
            resolved_spans = [
                {
                    "span_id": span.get("span_id"),
                    "evidence_id": span.get("evidence_id"),
                    "source": span.get("source"),
                    "text": span.get("text"),
                    "kind": span.get("kind"),
                    "provenance_method": "span",
                }
                for _, span in valid_span_pairs
            ]
            provenance_method = "span" if resolved_spans else None
            evidence_text = "\n".join(str(span.get("text") or "") for _, span in valid_span_pairs)
        else:
            quote_issues, resolved_spans, provenance_method = _quote_issues(
                raw_claim.get("supporting_quotes"), cited
            )
            issues.extend(quote_issues)
            evidence_text = "\n".join(str(item.get("content") or "") for item in cited)
        missing_numbers = [
            number for number in _numbers(text)
            if not _number_supported(number, evidence_text)
        ]
        if missing_numbers:
            issues.append("one or more claim numbers are absent from cited evidence")
        checked_claim = {
            "text": text,
            "evidence_ids": evidence_ids,
            "evidence_span_ids": span_ids,
            "evidence_spans": resolved_spans,
            "supporting_quotes": raw_claim.get("supporting_quotes") or [],
            "provenance_method": provenance_method,
            "structurally_supported": not issues,
            "supported": not issues,
            "entailment_checked": False,
            "issues": issues,
        }
        if raw_claim.get("repair_id"):
            checked_claim["repair_id"] = str(raw_claim["repair_id"])
        checked_claims.append(checked_claim)

    declared_gaps = [str(value) for value in (payload.get("gaps") or []) if str(value).strip()]
    fallback_answer = str(payload.get("answer") or "").strip()
    return _finalize_assessment(action, checked_claims, declared_gaps, fallback_answer)


def repair_prompt(
    question: str,
    assessment: dict[str, Any],
    catalog: list[dict[str, Any]],
) -> str:
    failed = []
    for claim in assessment.get("claims") or []:
        if not claim.get("structurally_supported"):
            failed.append({
                "repair_id": f"R{len(failed) + 1}",
                "text": claim.get("text"),
                "issues": claim.get("issues") or [],
            })
    return (
        "Repair only the failed claims below. Passing claims are already preserved and "
        "must not be repeated. Never invent an evidence span ID. Include the matching "
        "repair_id on every returned claim. Return only the required JSON object.\n\n"
        f"Question:\n{question}\n\n"
        f"Failed claims:\n{json.dumps(failed, indent=2)}\n\n"
        f"Available evidence:\n{format_evidence_for_prompt(catalog)}"
    )


def _declared_gaps(assessment: dict[str, Any]) -> list[str]:
    claim_issues = {
        issue
        for claim in assessment.get("claims") or []
        for issue in claim.get("issues") or []
    }
    return [gap for gap in assessment.get("gaps") or [] if gap not in claim_issues]


def _merge_repair(
    original: dict[str, Any],
    repaired: dict[str, Any],
) -> dict[str, Any]:
    merged_claims = list(original.get("claims") or [])
    failed_indexes = [
        index for index, claim in enumerate(merged_claims)
        if not claim.get("structurally_supported")
    ]
    repaired_claims = list(repaired.get("claims") or [])
    identified = {
        str(claim.get("repair_id")): claim
        for claim in repaired_claims
        if claim.get("repair_id")
    }
    if identified:
        for repair_index, claim_index in enumerate(failed_indexes, 1):
            replacement = identified.get(f"R{repair_index}")
            if replacement is not None:
                merged_claims[claim_index] = replacement
    else:
        # Legacy repair responses have no repair IDs; preserve their positional behavior.
        for index, replacement in zip(failed_indexes, repaired_claims):
            merged_claims[index] = replacement
    for claim in merged_claims:
        claim.pop("repair_id", None)
    declared_gaps = list(dict.fromkeys(
        _declared_gaps(original) + _declared_gaps(repaired)
    ))
    merged = _finalize_assessment(
        str(original.get("action") or "answer"),
        merged_claims,
        declared_gaps,
        "",
    )
    merged["repair_attempted"] = True
    return merged


def check_and_repair(
    complete: Callable[[str, str], str],
    question: str,
    draft: str,
    catalog: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Assess one structured draft and make at most one repair call."""
    assessment = assess_structured_draft(draft, catalog)
    if (
        assessment["checked"]
        and assessment["action"] == "answer"
        and assessment["status"] in {"partially_supported", "insufficient"}
        and any(
            not claim.get("structurally_supported")
            for claim in assessment.get("claims") or []
        )
    ):
        try:
            repaired_draft = complete(
                EVIDENCE_OUTPUT_INSTRUCTIONS,
                repair_prompt(question, assessment, catalog),
            )
            repaired = assess_structured_draft(repaired_draft, catalog)
            repaired["repair_attempted"] = True
            if repaired["checked"]:
                assessment = _merge_repair(assessment, repaired)
            else:
                assessment = _finalize_assessment(
                    str(assessment.get("action") or "answer"),
                    list(assessment.get("claims") or []),
                    _declared_gaps(assessment) + ["repair response could not be checked"],
                    "",
                )
                assessment["repair_attempted"] = True
        except Exception as exc:  # provider boundary: preserve checked portions
            assessment = _finalize_assessment(
                str(assessment.get("action") or "answer"),
                list(assessment.get("claims") or []),
                _declared_gaps(assessment) + [
                    f"repair unavailable: {type(exc).__name__}"
                ],
                "",
            )
            assessment["repair_attempted"] = True
    return str(assessment["answer"]), assessment


EVIDENCE_OUTPUT_INSTRUCTIONS = """
When you are ready to answer (and are not requesting a tool), return only JSON:
{"action":"answer|clarify|refuse","claims":[{"text":"one complete user-facing factual sentence","evidence_span_ids":["D1:S1","T1:S2"]}],"gaps":["missing fact, if any"],"answer":"clarification or refusal text only"}
Use only evidence span IDs shown in Retrieved context. Every factual or numeric sentence
must be a claim. Cite the smallest complete evidence spans that support it; the
program resolves their canonical source text, so do not copy quotations. Preserve
method, mesh, applicability, and NOT VERIFIED caveats. Resolve conflicts by
authority, applicability, and conditions—never retrieval rank. Q1 supports only
the user's premise, not its truth. If evidence is missing, omit the claim and name
the gap; clarify ambiguity and refuse unsupported or unsafe requests.
""".strip()
