"""H9: retrieval metrics — hit@4 and MRR over labeled queries."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.retrieval_metrics import (
    evaluate_retrieval,
    load_labels,
    run_retrieval_metrics,
)


def _fake_retrieve(ranked_by_query: dict[str, list[str]]):
    def retrieve(query: str, k: int = 4):
        return [
            {"source": source, "score": 0.9 - idx * 0.1}
            for idx, source in enumerate(ranked_by_query.get(query, []))
        ]

    return retrieve


def test_perfect_ranking_scores_one():
    labels = [
        {"query": "q1", "expected_sources": ["docs/a.md"]},
        {"query": "q2", "expected_sources": ["docs/b.md", "docs/c.md"]},
    ]
    out = evaluate_retrieval(
        labels, _fake_retrieve({"q1": ["docs/a.md", "docs/x.md"], "q2": ["docs/b.md"]})
    )
    assert out["hit_rate_at_4"] == 1.0
    assert out["mrr"] == 1.0
    assert out["queries"] == 2


def test_relevant_at_rank_three_gives_third_reciprocal():
    labels = [{"query": "q", "expected_sources": ["docs/target.md"]}]
    out = evaluate_retrieval(
        labels, _fake_retrieve({"q": ["docs/1.md", "docs/2.md", "docs/target.md"]})
    )
    assert out["hit_rate_at_4"] == 1.0
    assert out["mrr"] == round(1 / 3, 4)


def test_no_relevant_hit_scores_zero():
    labels = [{"query": "q", "expected_sources": ["docs/target.md"]}]
    out = evaluate_retrieval(
        labels, _fake_retrieve({"q": ["docs/1.md", "docs/2.md", "docs/3.md", "docs/4.md"]})
    )
    assert out["hit_rate_at_4"] == 0.0
    assert out["mrr"] == 0.0
    row = out["per_query"][0]
    assert row["first_relevant_rank"] is None


def test_relevant_outside_top_k_does_not_count():
    labels = [{"query": "q", "expected_sources": ["docs/target.md"]}]
    ranked = {f"docs/{i}.md" for i in range(10)} - {"docs/target.md"}
    ordered = [f"docs/{i}.md" for i in range(4)] + ["docs/target.md"]
    out = evaluate_retrieval(labels, _fake_retrieve({"q": ordered}))
    assert out["hit_rate_at_4"] == 0.0


def test_labels_file_has_twenty_valid_queries():
    labels = load_labels()
    assert len(labels) >= 20
    for item in labels:
        assert item["query"]
        assert item["expected_sources"]
        assert all(s.startswith("docs/") for s in item["expected_sources"])


def test_real_metrics_are_deterministic_and_strong():
    """Key-less + deterministic: same store, same numbers; hit@4 must hold 90%+."""
    first = run_retrieval_metrics()
    second = run_retrieval_metrics()
    assert first == second
    assert first["queries"] >= 20
    assert first["hit_rate_at_4"] >= 0.9, first["per_query"]
