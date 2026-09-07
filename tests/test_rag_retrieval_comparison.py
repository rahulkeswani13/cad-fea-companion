from eval.run_rag_retrieval_comparison import select_profile


def row(profile, critical, recall, ndcg, available=True):
    return {
        "profile": profile,
        "available": available,
        "critical_evidence_recall_at_4": critical,
        "metrics": {
            "answerable_evidence_recall_at_k": recall,
            "ndcg_at_k": ndcg,
        },
    }


def test_selection_prioritizes_critical_recall_before_mean_quality():
    rows = [
        row("lexical", 0.8, 0.95, 0.9),
        row("lexical_embedding", 0.9, 0.8, 0.8),
    ]
    assert select_profile(rows) == "lexical_embedding"


def test_selection_uses_simplicity_as_final_tiebreaker():
    rows = [
        row("lexical", 0.9, 0.9, 0.9),
        row("reranked", 0.9, 0.9, 0.9),
    ]
    assert select_profile(rows) == "lexical"


def test_selection_ignores_unavailable_profile():
    rows = [
        row("lexical", 0.8, 0.8, 0.8),
        row("reranked", 1.0, 1.0, 1.0, available=False),
    ]
    assert select_profile(rows) == "lexical"
