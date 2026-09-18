from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

from eval import run_rag_answer_evaluation as answer_eval
from eval.judge import rag_answer_judge_prompt


def test_answer_inputs_reuse_one_time_hidden_retrieval_without_rerun():
    fixture, report, materialized = answer_eval.load_frozen_inputs()
    assert report["profiles"]["reranked"]["query_call_count"] == 30
    assert len(materialized) == len(fixture["cases"]) == 30
    assert all(len(value["hits"]) == 4 for value in materialized.values())


def test_answer_inputs_reject_changed_retrieval_report(tmp_path):
    changed = tmp_path / "changed.json"
    payload = json.loads(answer_eval.RETRIEVAL_REPORT_PATH.read_text(encoding="utf-8"))
    payload["experimental_gate"]["passed"] = False
    changed.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(answer_eval.AnswerEvaluationError, match="report changed"):
        answer_eval.load_frozen_inputs(report_path=changed)


def test_answer_cache_key_covers_case_evidence_model_and_frozen_report():
    case = {"id": "x", "query": "yield?", "expected_behavior": "answer"}
    evidence = [{"evidence_id": "D1", "content": "250 MPa"}]
    original = answer_eval._cache_key(case, evidence, "model")
    assert answer_eval._cache_key({**case, "query": "density?"}, evidence, "model") != original
    assert answer_eval._cache_key(case, [{**evidence[0], "content": "276 MPa"}], "model") != original
    assert answer_eval._cache_key(case, evidence, "other-model") != original


def test_answer_summary_keeps_manual_and_semantic_grading_pending():
    rows = [{
        "id": "x",
        "critical": True,
        "generation_status": "complete",
        "expected_behavior": "answer",
        "actual_action": "answer",
        "semantic_evaluation": {"verdict": "pending", "pass": None},
    }]
    summary = answer_eval.summarize(rows, 2)
    assert summary["structural_behavior_accuracy"] == 1.0
    assert summary["pending"] == 1
    assert summary["semantic_answer_accuracy"] is None
    assert summary["manual_review"] == "pending_all_30"
    assert summary["acceptance"] == "pending_generation"


def test_rag_judge_receives_evidence_and_reference_expectations():
    prompt = rag_answer_judge_prompt(
        {
            "query": "Is it safe?",
            "history": [],
            "expected_behavior": "refuse",
            "required_facts": ["fatigue is not verified"],
            "forbidden_claims": ["certified safe"],
            "numeric_expectations": [],
            "critical": True,
        },
        "Fatigue is not verified.",
        {"status": "insufficient"},
        [{"evidence_id": "D1", "content": "No fatigue validation."}],
        [],
    )
    assert "retrieved_evidence" in prompt
    assert "reference_expectations" in prompt
    assert "certified safe" in prompt


def test_answer_run_requires_explicit_free_eligibility_before_model_calls(tmp_path):
    args = argparse.Namespace(
        output=tmp_path / "report.json",
        cache=tmp_path / "cache.json",
        limit=1,
        confirm_free_eligible=False,
        judge=False,
        judge_model="judge",
    )
    with pytest.raises(answer_eval.AnswerEvaluationError, match="No model calls made"):
        answer_eval.run(args)
    assert not args.output.exists()
    assert not args.cache.exists()


def test_answer_run_respects_uncached_batch_limit(tmp_path, monkeypatch):
    calls = []

    class Provider:
        def complete(self, system, user):
            calls.append((system, user))
            return json.dumps({
                "action": "clarify",
                "claims": [],
                "gaps": ["more context required"],
                "answer": "Please clarify the intended part and load case.",
            })

    settings = SimpleNamespace(
        gemini_model="free-model",
        gemini_api_key="configured-for-test",
        llm_configured=lambda: True,
    )
    monkeypatch.setattr(answer_eval, "get_settings", lambda: settings)
    monkeypatch.setattr(answer_eval, "get_llm_provider", lambda unused: Provider())
    args = argparse.Namespace(
        output=tmp_path / "report.json",
        cache=tmp_path / "cache.json",
        limit=2,
        confirm_free_eligible=True,
        judge=False,
        judge_model="judge",
    )
    report = answer_eval.run(args)
    assert report["generated_this_run"] == 2
    assert report["summary"]["generated"] == 2
    assert report["summary"]["pending"] == 28
    completed = [
        row for row in report["rows"] if row["generation_status"] == "complete"
    ]
    assert completed[0]["evidence"][0]["evidence_id"] == "Q1"
    assert completed[0]["retrieval_query"]
    assert len(calls) == 2
    assert args.output.exists()
    assert args.cache.exists()
