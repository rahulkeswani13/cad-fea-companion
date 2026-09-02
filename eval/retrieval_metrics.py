"""H9 retrieval metrics: hit@k and MRR over labeled queries.

``eval/rag_labels.json`` maps ~20 queries to the source documents that
genuinely answer them. Metrics are computed key-less and deterministically
from the same hybrid TF-IDF+BM25 store the agent uses, and ride in the eval
report as ``retrieval`` — so retrieval quality is measured, not assumed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

DEFAULT_LABELS_PATH = Path(__file__).resolve().parent / "rag_labels.json"
DEFAULT_K = 4


def load_labels(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or DEFAULT_LABELS_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    labels = []
    for item in data:
        query = str(item["query"]).strip()
        sources = [str(s) for s in item.get("expected_sources") or [] if str(s).strip()]
        if query and sources:
            labels.append({"query": query, "expected_sources": sources})
    return labels


def _reciprocal_rank(ranks: list[int]) -> float:
    return 1.0 / min(ranks) if ranks else 0.0


def evaluate_retrieval(
    labels: list[dict[str, Any]],
    retrieve_fn: Callable[[str, int], list[dict[str, Any]]],
    k: int = DEFAULT_K,
) -> dict[str, Any]:
    """Score every labeled query: hit@k (any expected source in top-k) and MRR."""
    per_query: list[dict[str, Any]] = []
    hits = 0
    rr_sum = 0.0
    for item in labels:
        hits_list = retrieve_fn(item["query"], k) or []
        ranked = [str(h.get("source") or "") for h in hits_list]
        relevant_ranks = [
            idx + 1
            for idx, source in enumerate(ranked[:k])
            if source in item["expected_sources"]
        ]
        hit = bool(relevant_ranks)
        rr = _reciprocal_rank(relevant_ranks)
        hits += int(hit)
        rr_sum += rr
        per_query.append(
            {
                "query": item["query"],
                "expected": item["expected_sources"],
                "ranked_sources": ranked,
                "first_relevant_rank": min(relevant_ranks) if relevant_ranks else None,
                "hit_at_k": hit,
                "reciprocal_rank": round(rr, 4),
            }
        )
    total = len(per_query)
    return {
        "queries": total,
        "k": k,
        "hit_rate_at_4": round(hits / total, 4) if total else 0.0,
        "mrr": round(rr_sum / total, 4) if total else 0.0,
        "per_query": per_query,
    }


def run_retrieval_metrics(k: int = DEFAULT_K) -> dict[str, Any]:
    """Convenience entry: real store, real labels (used by run_eval)."""
    from companion.rag.store import retrieve

    return evaluate_retrieval(load_labels(), retrieve, k=k)
