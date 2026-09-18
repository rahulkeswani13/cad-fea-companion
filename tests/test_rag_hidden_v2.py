from __future__ import annotations

import copy
import sys

import pytest

from eval.run_rag_hidden_v2 import (
    HiddenEvaluationError,
    build_current_corpus,
    evaluate_cases,
    experimental_gate,
    load_fixture,
    main,
    retriever_fingerprint,
    validate_fixture,
)


@pytest.fixture(scope="module")
def hidden_context():
    fixture = load_fixture()
    store, corpus = build_current_corpus()
    return fixture, store, corpus, retriever_fingerprint()


def test_hidden_v2_fixture_integrity(hidden_context):
    fixture, store, corpus, retriever = hidden_context
    resolved = validate_fixture(
        fixture,
        store.chunks,
        current_corpus_fingerprint=corpus,
        current_retriever_fingerprint=retriever,
    )

    cases = fixture["cases"]
    assert len(cases) == len(resolved) == 30
    assert len({case["id"] for case in cases}) == 30
    assert {case["expected_behavior"] for case in cases} == {"answer", "clarify", "refuse"}
    assert sum(case["expected_behavior"] == "answer" for case in cases) == 20
    assert sum(bool(case["history"]) for case in cases) >= 4
    assert sum(case["critical"] for case in cases) >= 10
    assert {"factual", "paraphrase", "comparison", "follow_up", "ambiguity", "unsupported", "conflict", "adversarial"}.issubset(
        {case["category"] for case in cases}
    )
    for case in cases:
        assert case["required_facts"]
        assert case["forbidden_claims"]
        assert case["evidence_groups"]


def test_hidden_v2_all_exact_evidence_resolves(hidden_context):
    fixture, store, corpus, retriever = hidden_context
    resolved = validate_fixture(
        fixture,
        store.chunks,
        current_corpus_fingerprint=corpus,
        current_retriever_fingerprint=retriever,
    )
    for case in fixture["cases"]:
        groups = resolved[case["id"]]
        assert len(groups) == len(case["evidence_groups"])
        assert all(options for group in groups for options in group)


@pytest.mark.parametrize("drift", ["corpus", "retriever"])
def test_hidden_v2_rejects_fingerprint_drift(hidden_context, drift):
    fixture, store, corpus, retriever = hidden_context
    kwargs = {
        "current_corpus_fingerprint": corpus,
        "current_retriever_fingerprint": retriever,
    }
    kwargs[f"current_{drift}_fingerprint"] = "drifted"
    with pytest.raises(HiddenEvaluationError, match=f"{drift.capitalize()} drift"):
        validate_fixture(fixture, store.chunks, **kwargs)


def _metrics(*, recall: float, ndcg: float, critical: float, median: float):
    return {
        "answerable_evidence_recall_at_k": recall,
        "ndcg_at_k": ndcg,
        "critical_evidence_recall_at_k": critical,
        "timing": {"median_query_ms": median},
    }


def test_hidden_v2_gate_requires_every_approved_check():
    lexical = _metrics(recall=0.70, ndcg=0.60, critical=0.80, median=5.0)
    passing = _metrics(recall=0.75, ndcg=0.61, critical=0.80, median=499.99)
    gate = experimental_gate(passing, lexical)
    assert gate["passed"] is True
    assert gate["answerable_gain"] == pytest.approx(0.05)
    assert all(gate["checks"].values())

    failures = {
        "gain": _metrics(recall=0.7499, ndcg=0.61, critical=0.80, median=10.0),
        "ndcg": _metrics(recall=0.80, ndcg=0.60, critical=0.80, median=10.0),
        "critical": _metrics(recall=0.80, ndcg=0.70, critical=0.7999, median=10.0),
        "latency": _metrics(recall=0.80, ndcg=0.70, critical=0.90, median=500.0),
    }
    for candidate in failures.values():
        assert experimental_gate(candidate, lexical)["passed"] is False


def test_hidden_v2_calls_retriever_once_and_includes_history():
    calls = []
    cases = [{
        "id": "context_case",
        "query": "What about that one?",
        "history": [{"role": "user", "content": "Compare the UAV arm variants."}],
        "expected_behavior": "answer",
        "critical": True,
    }]
    resolved = {"context_case": [[{"relevant"}]]}

    def retrieve(query, k):
        calls.append((query, k))
        return [{"chunk_id": "relevant"}]

    metrics = evaluate_cases(cases, resolved, retrieve)
    assert calls == [
        ("user: Compare the UAV arm variants.\nuser: What about that one?", 4)
    ]
    assert metrics["query_call_count"] == 1
    assert metrics["evidence_recall_at_k"] == 1.0


def test_hidden_v2_validator_rejects_malformed_case_without_models(hidden_context):
    fixture, store, corpus, retriever = hidden_context
    malformed = copy.deepcopy(fixture)
    malformed["cases"][0]["expected_behavior"] = "guess"
    with pytest.raises(HiddenEvaluationError, match="expected_behavior"):
        validate_fixture(
            malformed,
            store.chunks,
            current_corpus_fingerprint=corpus,
            current_retriever_fingerprint=retriever,
        )


def test_hidden_v2_cli_refuses_to_overwrite_report(tmp_path, monkeypatch, capsys):
    output = tmp_path / "existing.json"
    output.write_text("preserve me\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["run_rag_hidden_v2.py", "--output", str(output)])

    with pytest.raises(SystemExit, match="2"):
        main()

    assert output.read_text(encoding="utf-8") == "preserve me\n"
    assert "refusing to overwrite" in capsys.readouterr().err
