import sys

import pytest

from eval.run_rag_retrieval_comparison import (
    development_gate,
    main,
    retriever_fingerprint,
    select_profile,
)


def row(profile, critical, recall, ndcg, available=True, median_ms=10.0):
    return {
        "profile": profile,
        "available": available,
        "critical_evidence_recall_at_4": critical,
        "metrics": {
            "answerable_evidence_recall_at_k": recall,
            "ndcg_at_k": ndcg,
        },
        "timing": {"median_query_ms": median_ms},
    }


def test_selection_prioritizes_critical_recall_before_mean_quality():
    rows = [
        row("lexical", 0.7, 0.7, 0.6),
        row("lexical_embedding", 0.9, 0.8, 0.8),
        row("reranked", 0.8, 0.9, 0.9),
    ]
    assert select_profile(rows) == "lexical_embedding"


def test_selection_uses_simplicity_as_final_tiebreaker():
    rows = [
        row("lexical", 0.7, 0.7, 0.6),
        row("lexical_embedding", 0.9, 0.8, 0.9),
        row("reranked", 0.9, 0.8, 0.9),
    ]
    assert select_profile(rows) == "lexical_embedding"


def test_selection_ignores_unavailable_profile():
    rows = [
        row("lexical", 0.8, 0.8, 0.8),
        row("reranked", 1.0, 1.0, 1.0, available=False),
    ]
    assert select_profile(rows) == "lexical"


def test_selection_requires_the_complete_experimental_gate():
    baseline = row("lexical", 0.7, 0.8, 0.6)
    too_small_gain = row("lexical_embedding", 0.9, 0.849, 0.8)
    too_slow = row("reranked", 0.9, 0.9, 0.8, median_ms=500.0)
    assert development_gate(too_small_gain, baseline)["eligible"] is False
    assert development_gate(too_slow, baseline)["eligible"] is False
    assert select_profile([baseline, too_small_gain, too_slow]) == "lexical"


def test_cli_rejects_retired_heldout_before_evaluation(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", [
        "run_rag_retrieval_comparison.py",
        "--output", str(tmp_path / "report.json"),
        "--run-heldout",
    ])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert not (tmp_path / "report.json").exists()


def test_retriever_fingerprint_changes_with_source_content(tmp_path):
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    before = retriever_fingerprint((first, second))
    assert before == retriever_fingerprint((second, first))
    second.write_text("changed", encoding="utf-8")
    assert retriever_fingerprint((first, second)) != before
