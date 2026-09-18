#!/usr/bin/env python3
"""Generate evidence-bounded answers from the immutable hidden-v2 retrieval report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from companion.config import get_settings  # noqa: E402
from companion.llm.providers import get_llm_provider  # noqa: E402
from companion.rag.evidence import (  # noqa: E402
    EVIDENCE_OUTPUT_INSTRUCTIONS,
    check_and_repair,
    evidence_catalog,
    format_evidence_for_prompt,
)
from eval.judge import judge_rag_answer_case, rag_answer_judge_prompt  # noqa: E402
from eval.run_rag_hidden_v2 import (  # noqa: E402
    build_current_corpus,
    load_fixture,
    retriever_fingerprint,
)

FIXTURE_PATH = ROOT / "eval" / "rag_hidden_v2.json"
RETRIEVAL_REPORT_PATH = ROOT / "eval" / "reports" / "rag_hidden_v2_retrieval.json"
DEFAULT_CACHE = ROOT / "data" / "results" / "rag_answer_cache.json"
EXPECTED_REPORT_SHA256 = "316e3c9c7a12846d187e754f4d93eaada3ce58b995a9336818a4335dbe5d78cb"
PROFILE = "reranked"
MAX_UNCACHED_PER_RUN = 10


class AnswerEvaluationError(ValueError):
    """The frozen answer-evaluation inputs are invalid or have drifted."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AnswerEvaluationError(f"expected JSON object: {path}")
    return payload


def load_frozen_inputs(
    fixture_path: Path = FIXTURE_PATH,
    report_path: Path = RETRIEVAL_REPORT_PATH,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Validate immutable retrieval evidence and materialize its ranked chunks."""
    if _sha256(report_path) != EXPECTED_REPORT_SHA256:
        raise AnswerEvaluationError(
            "hidden-v2 retrieval report changed; answers require the original one-time report"
        )
    fixture = load_fixture(fixture_path)
    report = _load_json(report_path)
    store, corpus = build_current_corpus()
    retriever = retriever_fingerprint()
    expected_corpus = fixture["metadata"]["corpus_fingerprint"]
    expected_retriever = fixture["metadata"]["retriever_fingerprint"]
    if corpus != expected_corpus or report.get("corpus_fingerprint") != expected_corpus:
        raise AnswerEvaluationError("corpus drift from hidden-v2 freeze")
    if retriever != expected_retriever or report.get("retriever_fingerprint") != expected_retriever:
        raise AnswerEvaluationError("retriever drift from hidden-v2 freeze")
    profile = (report.get("profiles") or {}).get(PROFILE) or {}
    rows = profile.get("per_query")
    if (
        profile.get("available") is not True
        or profile.get("query_call_count") != len(fixture["cases"])
        or not isinstance(rows, list)
    ):
        raise AnswerEvaluationError("one-time reranked retrieval results are incomplete")
    cases_by_id = {case["id"]: case for case in fixture["cases"]}
    rows_by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    if set(rows_by_id) != set(cases_by_id) or len(rows_by_id) != len(rows):
        raise AnswerEvaluationError("retrieval rows do not match hidden-v2 cases exactly")
    chunks_by_id = {chunk.chunk_id: chunk for chunk in store.chunks}
    materialized: dict[str, Any] = {}
    for case_id, row in rows_by_id.items():
        hits = []
        for chunk_id in row.get("ranked_chunk_ids") or []:
            chunk = chunks_by_id.get(chunk_id)
            if chunk is None:
                raise AnswerEvaluationError(f"{case_id}: saved chunk no longer exists: {chunk_id}")
            hits.append({
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "section_id": chunk.section_id,
                "text": chunk.text,
                "metadata": chunk.metadata,
            })
        if len(hits) != fixture["metadata"]["final_k"]:
            raise AnswerEvaluationError(f"{case_id}: expected exactly four frozen hits")
        materialized[case_id] = {
            "retrieval_query": row.get("retrieval_query"),
            "hits": hits,
        }
    return fixture, report, materialized


def _cache_key(
    case: dict[str, Any],
    evidence: list[dict[str, Any]],
    model: str,
) -> str:
    payload = {
        "case": case,
        "evidence": evidence,
        "model": model,
        "profile": PROFILE,
        "retrieval_report_sha256": EXPECTED_REPORT_SHA256,
        "prompt": EVIDENCE_OUTPUT_INSTRUCTIONS,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _judge_key(case: dict[str, Any], cached: dict[str, Any], model: str) -> str:
    payload = {
        "model": model,
        "prompt": rag_answer_judge_prompt(
            case,
            cached["answer"],
            cached["assessment"],
            cached["evidence"],
            [],
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 2, "entries": {}}
    payload = _load_json(path)
    if payload.get("schema_version") != 2 or not isinstance(payload.get("entries"), dict):
        raise AnswerEvaluationError("unsupported answer cache")
    return payload


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _actions_match(expected: str, actual: str) -> bool:
    if expected == "refuse":
        return actual in {"refuse", "abstain"}
    return expected == actual


def summarize(rows: list[dict[str, Any]], total_cases: int) -> dict[str, Any]:
    generated = [row for row in rows if row.get("generation_status") == "complete"]
    structural_behavior = [
        row for row in generated
        if _actions_match(row["expected_behavior"], row["actual_action"])
    ]
    graded = [
        row["semantic_evaluation"] for row in generated
        if (row.get("semantic_evaluation") or {}).get("verdict") == "graded"
    ]
    factual_claims = sum(int(item.get("factual_claims") or 0) for item in graded)
    supported_claims = sum(int(item.get("supported_claims") or 0) for item in graded)
    critical_numeric_violations = sum(
        item.get("critical_numeric_violation") is True for item in graded
    )
    complete = len(generated) == total_cases
    return {
        "cases": total_cases,
        "generated": len(generated),
        "pending": total_cases - len(generated),
        "structural_behavior_accuracy": (
            round(len(structural_behavior) / len(generated), 4) if generated else None
        ),
        "semantic_cases_graded": len(graded),
        "semantic_answer_accuracy": (
            round(sum(item.get("pass") is True for item in graded) / len(graded), 4)
            if graded else None
        ),
        "supported_factual_claim_rate": (
            round(supported_claims / factual_claims, 4) if factual_claims else None
        ),
        "critical_numeric_violations": critical_numeric_violations if graded else None,
        "manual_review": "pending_all_30",
        "acceptance": (
            "pending_semantic_and_manual_review" if complete else "pending_generation"
        ),
        "note": (
            "Structural checks validate canonical evidence spans, tool success, and exact "
            "numbers; exact or conservatively normalized quotes are a legacy fallback. "
            "They do not establish semantic entailment or engineering validity."
        ),
    }


def _generation_prompt(case: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    history = "\n".join(
        f"{turn['role']}: {turn['content']}" for turn in case.get("history") or []
    ) or "(none)"
    return (
        f"Conversation history:\n{history}\n\n"
        f"Current question:\n{case['query']}\n\n"
        f"Evidence:\n{format_evidence_for_prompt(evidence)}"
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not 1 <= args.limit <= MAX_UNCACHED_PER_RUN:
        raise AnswerEvaluationError("--limit must be between 1 and 10")
    if not args.confirm_free_eligible:
        raise AnswerEvaluationError(
            "No model calls made: verify free Gemini model/project eligibility, then pass "
            "--confirm-free-eligible"
        )
    settings = get_settings()
    if not settings.llm_configured():
        raise AnswerEvaluationError("No model calls made: GEMINI_API_KEY is not configured")

    fixture, _, frozen = load_frozen_inputs()
    cache = _load_cache(args.cache)
    provider = get_llm_provider(settings)
    generated_now = 0
    judged_now = 0
    rows = []
    for case in fixture["cases"]:
        evidence = evidence_catalog(
            frozen[case["id"]]["hits"], [], question=case["query"]
        )
        key = _cache_key(case, evidence, settings.gemini_model)
        cached = cache["entries"].get(key)
        if cached is None and generated_now < args.limit:
            draft = provider.complete(
                EVIDENCE_OUTPUT_INSTRUCTIONS,
                _generation_prompt(case, evidence),
            )
            answer, assessment = check_and_repair(
                provider.complete, case["query"], draft, evidence
            )
            cached = {
                "answer": answer,
                "assessment": assessment,
                "evidence": evidence,
                "retrieval_query": frozen[case["id"]]["retrieval_query"],
                "judges": {},
            }
            cache["entries"][key] = cached
            _save(args.cache, cache)
            generated_now += 1
        if cached is None:
            rows.append({
                "id": case["id"],
                "critical": case["critical"],
                "generation_status": "pending",
            })
            continue
        cached.setdefault("judges", {})
        judge_key = _judge_key(case, cached, args.judge_model)
        verdict = cached["judges"].get(judge_key)
        if args.judge and verdict is None and judged_now < args.limit:
            verdict = judge_rag_answer_case(
                case,
                cached["answer"],
                cached["assessment"],
                cached["evidence"],
                [],
                settings.gemini_api_key,
                args.judge_model,
            )
            cached["judges"][judge_key] = verdict
            _save(args.cache, cache)
            judged_now += 1
        assessment = cached["assessment"]
        rows.append({
            "id": case["id"],
            "critical": case["critical"],
            "generation_status": "complete",
            "expected_behavior": case["expected_behavior"],
            "actual_action": assessment["action"],
            "answer": cached["answer"],
            "assessment": assessment,
            "retrieval_query": cached["retrieval_query"],
            "evidence": cached["evidence"],
            "semantic_evaluation": verdict or {"verdict": "pending", "pass": None},
        })

    report = {
        "schema_version": 2,
        "fixture_id": fixture["metadata"]["fixture_id"],
        "corpus_fingerprint": fixture["metadata"]["corpus_fingerprint"],
        "retriever_fingerprint": fixture["metadata"]["retriever_fingerprint"],
        "retrieval_report_sha256": EXPECTED_REPORT_SHA256,
        "profile": PROFILE,
        "model": settings.gemini_model,
        "generated_this_run": generated_now,
        "judged_this_run": judged_now,
        "batch_limit": args.limit,
        "summary": summarize(rows, len(fixture["cases"])),
        "rows": rows,
    }
    _save(args.output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--confirm-free-eligible", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument(
        "--judge-model",
        default=os.environ.get("EVAL_JUDGE_MODEL", "gemini-3.5-flash-lite"),
    )
    args = parser.parse_args()
    try:
        report = run(args)
    except AnswerEvaluationError as exc:
        parser.error(str(exc))
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
