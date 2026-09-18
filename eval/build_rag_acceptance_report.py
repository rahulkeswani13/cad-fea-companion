"""Build the aggregate RAG acceptance handoff without exposing hidden cases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVELOPMENT = ROOT / "eval" / "reports" / "rag_retrieval_comparison.json"
DEFAULT_HIDDEN = ROOT / "eval" / "reports" / "rag_hidden_v2_retrieval.json"
MANUAL_BOOL_FIELDS = (
    "behavior_correct",
    "required_facts_present",
    "numeric_units_correct",
    "forbidden_claim_absent",
    "citations_entailed",
    "caveats_adjacent",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def summarize_manual_review(
    manual_review: dict[str, Any] | None,
    answer: dict[str, Any] | None,
    *,
    answer_report_sha256: str | None = None,
) -> dict[str, Any]:
    """Derive human-review metrics from per-case marks; never trust aggregates."""
    result = {
        "status": "pending",
        "reviewer_type": None,
        "reviewed_cases": 0,
        "behavior_accuracy": None,
        "supported_factual_claim_rate": None,
        "critical_numeric_violations": None,
        "validation_errors": [],
    }
    if not manual_review:
        return result
    result["reviewer_type"] = manual_review.get("reviewer_type")
    if not answer:
        result["validation_errors"].append("manual review has no answer report")
        return result
    if answer_report_sha256 and manual_review.get("answer_report_sha256") != answer_report_sha256:
        result["validation_errors"].append("manual review is not bound to this answer report")

    answer_rows = [
        row for row in (answer.get("rows") or [])
        if isinstance(row, dict) and row.get("generation_status") == "complete"
    ]
    answer_by_id = {
        str(row.get("id")): row for row in answer_rows if str(row.get("id") or "")
    }
    reviews = manual_review.get("reviews")
    if not isinstance(reviews, list):
        result["validation_errors"].append("manual review rows are missing")
        return result
    review_ids = [
        str(row.get("id")) for row in reviews
        if isinstance(row, dict) and str(row.get("id") or "")
    ]
    if len(review_ids) != len(set(review_ids)):
        result["validation_errors"].append("manual review contains duplicate case IDs")
    if set(review_ids) != set(answer_by_id):
        result["validation_errors"].append("manual review case set does not match generated answers")

    valid_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    invalid_rows = 0
    for review in reviews:
        if not isinstance(review, dict):
            invalid_rows += 1
            continue
        answer_row = answer_by_id.get(str(review.get("id") or ""))
        factual = review.get("factual_claims")
        supported = review.get("supported_factual_claims")
        violations = review.get("critical_numeric_violations")
        valid = bool(
            answer_row
            and all(isinstance(review.get(field), bool) for field in MANUAL_BOOL_FIELDS)
            and _nonnegative_int(factual)
            and _nonnegative_int(supported)
            and supported <= factual
            and _nonnegative_int(violations)
        )
        if valid:
            valid_rows.append((review, answer_row))
        else:
            invalid_rows += 1
    if invalid_rows:
        result["validation_errors"].append(
            f"manual review has {invalid_rows} incomplete or invalid row(s)"
        )

    reviewed = len(valid_rows)
    factual_claims = sum(row[0]["factual_claims"] for row in valid_rows)
    supported_claims = sum(row[0]["supported_factual_claims"] for row in valid_rows)
    result.update({
        "reviewed_cases": reviewed,
        "behavior_accuracy": (
            round(sum(row[0]["behavior_correct"] for row in valid_rows) / reviewed, 4)
            if reviewed else None
        ),
        "supported_factual_claim_rate": (
            round(supported_claims / factual_claims, 4) if factual_claims else None
        ),
        "critical_numeric_violations": (
            sum(
                row[0]["critical_numeric_violations"]
                for row in valid_rows
                if row[1].get("critical") is True
            )
            if reviewed else None
        ),
    })
    if (
        manual_review.get("status") == "complete"
        and reviewed == 30
        and len(answer_by_id) == 30
        and not result["validation_errors"]
    ):
        result["status"] = "complete"
    return result


def _development_profile(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("metrics") or {}
    return {
        "profile": row.get("profile"),
        "available": row.get("available"),
        "critical_evidence_recall_at_4": row.get("critical_evidence_recall_at_4"),
        "answerable_evidence_recall_at_4": metrics.get("answerable_evidence_recall_at_k"),
        "precision_at_4": metrics.get("precision_at_k"),
        "ndcg_at_4": metrics.get("ndcg_at_k"),
        "timing": row.get("timing") or {},
    }


def _hidden_profile(profile: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": profile,
        "available": row.get("available"),
        "critical_evidence_recall_at_4": row.get("critical_evidence_recall_at_k"),
        "answerable_evidence_recall_at_4": row.get("answerable_evidence_recall_at_k"),
        "precision_at_4": row.get("evidence_precision_at_k"),
        "ndcg_at_4": row.get("ndcg_at_k"),
        "timing": row.get("timing") or {},
    }


def build_report(
    development: dict[str, Any],
    hidden: dict[str, Any],
    answer: dict[str, Any] | None = None,
    manual_review: dict[str, Any] | None = None,
    *,
    answer_report_sha256: str | None = None,
) -> dict[str, Any]:
    """Return stable aggregate status; never copy hidden per-query rows."""
    hidden_profiles = hidden.get("profiles") or {}
    selected_name = development.get("selected_profile") or "reranked"
    selected = _hidden_profile(selected_name, hidden_profiles.get(selected_name) or {})
    retrieval_pass = bool(
        selected.get("available") is True
        and (selected.get("answerable_evidence_recall_at_4") or 0) >= 0.9
        and (selected.get("critical_evidence_recall_at_4") or 0) >= 1.0
        and (selected.get("timing") or {}).get("median_query_ms", float("inf")) < 500
    )

    answer_summary = (answer or {}).get("summary") or {}
    generated_rows = [
        row for row in ((answer or {}).get("rows") or [])
        if isinstance(row, dict) and row.get("generation_status") == "complete"
    ]
    answers_complete = bool(
        answer_summary.get("generated") == 30
        and len(generated_rows) == 30
        and len({row.get("id") for row in generated_rows}) == 30
    )
    semantic_complete = answer_summary.get("semantic_cases_graded") == 30
    manual = summarize_manual_review(
        manual_review,
        answer,
        answer_report_sha256=answer_report_sha256,
    )
    review_complete = manual["status"] == "complete"
    human_review_complete = bool(
        review_complete and manual["reviewer_type"] == "human"
    )
    answer_quality_pass = bool(
        answers_complete
        and review_complete
        and (manual["behavior_accuracy"] or 0) >= 0.9
        and (manual["supported_factual_claim_rate"] or 0) >= 0.95
        and manual["critical_numeric_violations"] == 0
    )
    answer_pass = human_review_complete and answer_quality_pass

    failures = []
    if not retrieval_pass:
        failures.append(
            "Independent retrieval misses the 90% answerable-recall and/or "
            "100% critical-recall target."
        )
    if not answers_complete:
        failures.append("Hidden-v2 answer generation is incomplete.")
    if answers_complete and not semantic_complete:
        failures.append("Advisory semantic/citation grading is incomplete.")
    if not review_complete:
        failures.append("Manual review of all 30 hidden-v2 final answers is incomplete.")
    elif not human_review_complete:
        failures.append(
            "The delegated AI review is complete but is not independent human sign-off."
        )
    if answers_complete and review_complete and not answer_quality_pass:
        failures.append("Answer behavior, factual support, or critical-number targets failed.")

    return {
        "schema_version": 2,
        "accepted": retrieval_pass and answer_pass,
        "selected_profile": selected_name,
        "configuration": development.get("configuration") or {},
        "development": [
            _development_profile(row) for row in development.get("development") or []
        ],
        "independent_hidden": {
            "fixture_id": hidden.get("fixture_id"),
            "profiles": [
                _hidden_profile(name, row)
                for name, row in hidden_profiles.items()
            ],
            "experimental_gate": hidden.get("experimental_gate") or {},
        },
        "answer_evaluation": {
            "generated": answer_summary.get("generated", 0),
            "semantic_cases_graded": answer_summary.get("semantic_cases_graded", 0),
            "structural_behavior_accuracy": answer_summary.get("structural_behavior_accuracy"),
            "advisory_supported_factual_claim_rate": answer_summary.get("supported_factual_claim_rate"),
            "advisory_critical_numeric_violations": answer_summary.get("critical_numeric_violations"),
            "manual_reviewed_cases": manual["reviewed_cases"],
            "manual_reviewer_type": manual["reviewer_type"],
            "manual_behavior_accuracy": manual["behavior_accuracy"],
            "manual_supported_factual_claim_rate": manual["supported_factual_claim_rate"],
            "manual_critical_numeric_violations": manual["critical_numeric_violations"],
            "manual_review_validation_errors": manual["validation_errors"],
        },
        "targets": {
            "answerable_evidence_recall_at_4": 0.9,
            "critical_evidence_recall_at_4": 1.0,
            "median_retrieval_ms_below": 500,
            "answer_behavior_accuracy": 0.9,
            "supported_factual_claim_rate": 0.95,
            "critical_numeric_violations": 0,
            "manual_reviewed_cases": 30,
        },
        "checks": {
            "retrieval": "pass" if retrieval_pass else "fail",
            "answer_evaluation": (
                "pass"
                if answer_pass
                else "fail"
                if answers_complete and review_complete and not answer_quality_pass
                else "pending"
            ),
            "semantic_judge": "complete" if semantic_complete else "pending",
            "manual_review": (
                "complete"
                if human_review_complete
                else "delegated_ai_complete"
                if review_complete
                else "pending"
            ),
        },
        "failure_analysis": failures,
        "restrictions": {
            "hidden_case_details_included": False,
            "historical_heldout_not_run": True,
            "hidden_retrieval_not_rerun": True,
            "answer_report_included": bool(answer),
            "manual_review_included": bool(manual_review),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", type=Path, default=DEFAULT_DEVELOPMENT)
    parser.add_argument("--hidden", type=Path, default=DEFAULT_HIDDEN)
    parser.add_argument("--answer", type=Path)
    parser.add_argument("--manual-review", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    development = json.loads(args.development.read_text(encoding="utf-8"))
    hidden = json.loads(args.hidden.read_text(encoding="utf-8"))
    answer = json.loads(args.answer.read_text(encoding="utf-8")) if args.answer else None
    manual = (
        json.loads(args.manual_review.read_text(encoding="utf-8"))
        if args.manual_review else None
    )
    answer_sha256 = _sha256(args.answer) if args.answer else None
    rendered = json.dumps(
        build_report(
            development,
            hidden,
            answer,
            manual,
            answer_report_sha256=answer_sha256,
        ),
        indent=2,
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
