import hashlib
import json
from pathlib import Path

import pytest

from eval.build_rag_acceptance_report import build_report
from eval.create_rag_manual_review import (
    ManualReviewTemplateError,
    build_template,
    render_markdown,
)


def _development():
    return {
        "selected_profile": "reranked",
        "configuration": {"final_k": 4},
        "development": [],
    }


def _hidden(answerable=0.8, critical=0.775, median=350):
    return {
        "fixture_id": "fresh",
        "profiles": {
            "reranked": {
                "available": True,
                "answerable_evidence_recall_at_k": answerable,
                "critical_evidence_recall_at_k": critical,
                "evidence_precision_at_k": 0.25,
                "ndcg_at_k": 0.7,
                "timing": {"median_query_ms": median},
                "per_query": [{"id": "hidden"}],
            }
        },
        "experimental_gate": {"passed": True},
    }


def _answer():
    return {
        "summary": {
            "generated": 30,
            "semantic_cases_graded": 30,
            "structural_behavior_accuracy": 0.9,
            "supported_factual_claim_rate": 0.95,
            "critical_numeric_violations": 0,
        },
        "rows": [
            {
                "id": f"case-{index:02d}",
                "critical": index <= 20,
                "generation_status": "complete",
            }
            for index in range(1, 31)
        ],
    }


def _manual():
    return {
        "status": "complete",
        "reviewer_type": "human",
        "reviews": [
            {
                "id": f"case-{index:02d}",
                "behavior_correct": index > 3,
                "required_facts_present": True,
                "numeric_units_correct": True,
                "forbidden_claim_absent": True,
                "citations_entailed": True,
                "caveats_adjacent": True,
                "factual_claims": 20,
                "supported_factual_claims": 19,
                "critical_numeric_violations": 0,
            }
            for index in range(1, 31)
        ],
    }


def test_report_is_not_accepted_while_retrieval_fails_and_answers_pending():
    report = build_report(_development(), _hidden())
    assert report["accepted"] is False
    assert report["checks"]["retrieval"] == "fail"
    assert report["checks"]["answer_evaluation"] == "pending"


def test_report_never_copies_hidden_per_query_details():
    report = build_report(_development(), _hidden())
    assert "per_query" not in json.dumps(report)
    assert "hidden" not in str(report["independent_hidden"]["profiles"])
    assert report["restrictions"]["hidden_case_details_included"] is False


def test_acceptance_requires_retrieval_answer_and_manual_review():
    hidden = _hidden(answerable=0.9, critical=1.0, median=499.9)
    report = build_report(_development(), hidden, _answer(), _manual())
    assert report["accepted"] is True
    assert report["answer_evaluation"]["manual_behavior_accuracy"] == 0.9
    assert report["answer_evaluation"]["manual_supported_factual_claim_rate"] == 0.95
    assert report["checks"] == {
        "retrieval": "pass",
        "answer_evaluation": "pass",
        "semantic_judge": "complete",
        "manual_review": "complete",
    }


def test_manual_complete_flag_without_human_scores_cannot_pass():
    hidden = _hidden(answerable=0.9, critical=1.0, median=499.9)
    manual = {
        "status": "complete",
        "reviewed_cases": 30,
        "behavior_accuracy": 1.0,
        "supported_factual_claim_rate": 1.0,
        "critical_numeric_violations": 0,
    }
    report = build_report(_development(), hidden, _answer(), manual)
    assert report["accepted"] is False
    assert report["checks"]["manual_review"] == "pending"
    assert report["checks"]["answer_evaluation"] == "pending"


def test_manual_review_is_bound_to_exact_answer_report():
    hidden = _hidden(answerable=0.9, critical=1.0, median=499.9)
    manual = _manual()
    manual["answer_report_sha256"] = "wrong"
    report = build_report(
        _development(),
        hidden,
        _answer(),
        manual,
        answer_report_sha256="expected",
    )
    assert report["accepted"] is False
    assert report["checks"]["manual_review"] == "pending"
    assert report["answer_evaluation"]["manual_review_validation_errors"] == [
        "manual review is not bound to this answer report"
    ]


def test_delegated_ai_review_can_record_failure_but_never_accept():
    hidden = _hidden(answerable=0.9, critical=1.0, median=499.9)
    manual = _manual()
    manual["reviewer_type"] = "delegated_ai"
    report = build_report(_development(), hidden, _answer(), manual)
    assert report["accepted"] is False
    assert report["checks"]["manual_review"] == "delegated_ai_complete"
    assert report["checks"]["answer_evaluation"] == "pending"
    assert "not independent human sign-off" in " ".join(report["failure_analysis"])


def test_manual_review_template_is_hash_bound_and_pending():
    template = build_template(_answer(), "abc123")
    assert template["answer_report_sha256"] == "abc123"
    assert template["status"] == "pending"
    assert len(template["reviews"]) == 30
    assert template["reviews"][0]["behavior_correct"] is None
    assert "Answer report SHA-256: `abc123`" in render_markdown(template)


def test_manual_review_template_rejects_incomplete_generation():
    answer = _answer()
    answer["rows"].pop()
    with pytest.raises(ManualReviewTemplateError, match="exactly 30"):
        build_template(answer, "abc123")


def test_current_acceptance_summary_is_reproducible(tmp_path):
    root = Path(__file__).resolve().parents[1]
    development = json.loads(
        (root / "eval/reports/rag_retrieval_comparison.json").read_text()
    )
    hidden = json.loads(
        (root / "eval/reports/rag_hidden_v2_retrieval.json").read_text()
    )
    answer_path = root / "eval/reports/rag_hidden_v2_answers.json"
    answer = json.loads(answer_path.read_text())
    manual = json.loads(
        (root / "eval/reviews/rag_hidden_v2_ai_review.json").read_text()
    )
    report = build_report(
        development,
        hidden,
        answer,
        manual,
        answer_report_sha256=hashlib.sha256(answer_path.read_bytes()).hexdigest(),
    )
    committed = json.loads(
        (root / "eval/reports/rag_acceptance_summary.json").read_text()
    )
    assert report == committed
    assert report["accepted"] is False
    assert report["checks"]["retrieval"] == "fail"
    assert report["checks"]["answer_evaluation"] == "fail"
    assert report["answer_evaluation"]["generated"] == 30
