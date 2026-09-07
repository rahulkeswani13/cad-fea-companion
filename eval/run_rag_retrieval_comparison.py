#!/usr/bin/env python3
"""Compare fixed lexical, local embedding, and cross-encoder RAG profiles."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from companion.rag.neural import (  # noqa: E402
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_REVISION,
    PROFILES,
    RERANKER_MODEL_ID,
    RERANKER_MODEL_REVISION,
    NeuralRetriever,
    load_models,
)
from companion.rag.store import get_store, ingest_docs  # noqa: E402
from eval.benchmark import (  # noqa: E402
    benchmark_hash,
    evaluate_evidence,
    load_benchmark,
    require_review,
    resolve_relevance,
)

COMPLEXITY = {"lexical": 0, "lexical_embedding": 1, "reranked": 2}


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _critical_recall(metrics: dict[str, Any]) -> float | None:
    return _mean([
        row["evidence_recall"] for row in metrics["per_query"]
        if row["critical"] and row["evidence_recall"] is not None
    ])


def _timing(values: list[float], load_ms: float) -> dict[str, Any]:
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1)) if ordered else 0
    return {
        "model_load_ms": round(load_ms, 2),
        "queries": len(values),
        "mean_query_ms": round(statistics.mean(values), 2) if values else None,
        "median_query_ms": round(statistics.median(values), 2) if values else None,
        "p95_query_ms": round(ordered[p95_index], 2) if ordered else None,
    }


def evaluate_profile(
    benchmark: dict[str, Any],
    split: str,
    profile: str,
    *,
    allow_download: bool,
) -> dict[str, Any]:
    store = get_store()
    load_start = perf_counter()
    models = None
    if profile != "lexical":
        try:
            models = load_models(profile, local_files_only=not allow_download)
        except Exception as exc:  # availability is a result, never a lexical score
            return {
                "profile": profile,
                "available": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "timing": _timing([], (perf_counter() - load_start) * 1000.0),
            }
    load_ms = (perf_counter() - load_start) * 1000.0
    retriever = NeuralRetriever(store, models)
    timings: list[float] = []

    def retrieve(query: str, k: int) -> list[dict[str, Any]]:
        detail = retriever.search_detail(query, profile=profile, k=k, strict=True)
        status = detail["retrieval"]
        timings.append(float(status["timing_ms"]))
        if status["active_profile"] == "unavailable":
            raise RuntimeError(status.get("reason") or "profile unavailable")
        return detail["fused"]

    cases = [case for case in benchmark["cases"] if case["split"] == split]
    try:
        metrics = evaluate_evidence(resolve_relevance(cases, store.chunks), retrieve, k=4)
    except Exception as exc:
        return {
            "profile": profile,
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "timing": _timing(timings, load_ms),
        }
    return {
        "profile": profile,
        "available": True,
        "critical_evidence_recall_at_4": _critical_recall(metrics),
        "timing": _timing(timings, load_ms),
        "metrics": metrics,
    }


def select_profile(rows: list[dict[str, Any]]) -> str:
    available = [row for row in rows if row.get("available")]
    if not available:
        raise ValueError("No retrieval profile is available")

    def key(row: dict[str, Any]) -> tuple[float, float, float, int]:
        metrics = row["metrics"]
        return (
            float(row.get("critical_evidence_recall_at_4") or 0.0),
            float(metrics.get("answerable_evidence_recall_at_k") or 0.0),
            float(metrics.get("ndcg_at_k") or 0.0),
            -COMPLEXITY[row["profile"]],
        )

    return max(available, key=key)["profile"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download-models", action="store_true")
    parser.add_argument("--run-heldout", action="store_true")
    args = parser.parse_args()

    benchmark = load_benchmark()
    require_review(benchmark)
    ingest = ingest_docs(reuse_if_unchanged=True)
    if not ingest["ok"]:
        raise SystemExit(ingest["error"])
    if ingest["fingerprint"] != benchmark["corpus_fingerprint"]:
        raise SystemExit("Corpus drift: benchmark approval no longer matches the index")

    development = [
        evaluate_profile(
            benchmark, "development", profile,
            allow_download=args.download_models,
        )
        for profile in PROFILES
    ]
    selected = select_profile(development)
    report: dict[str, Any] = {
        "schema_version": 1,
        "benchmark_hash": benchmark_hash(benchmark),
        "corpus_fingerprint": benchmark["corpus_fingerprint"],
        "selection_order": [
            "critical_evidence_recall_at_4",
            "answerable_evidence_recall_at_4",
            "ndcg_at_4",
            "simplicity",
        ],
        "configuration": {
            "candidates_per_retriever": 10,
            "rrf_k": 60,
            "final_k": 4,
            "timing_note": (
                "Process-order wall timings; later profiles may reuse framework, "
                "model, and operating-system caches."
            ),
            "embedding_model": {
                "id": EMBEDDING_MODEL_ID,
                "revision": EMBEDDING_MODEL_REVISION,
            },
            "reranker_model": {
                "id": RERANKER_MODEL_ID,
                "revision": RERANKER_MODEL_REVISION,
            },
        },
        "development": development,
        "selected_profile": selected,
        "heldout": None,
        "heldout_run_count": 0,
    }
    if args.run_heldout:
        report["heldout"] = evaluate_profile(
            benchmark, "heldout", selected, allow_download=args.download_models
        )
        report["heldout_run_count"] = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "selected_profile": selected,
        "heldout_run_count": report["heldout_run_count"],
        "development": [
            {
                "profile": row["profile"],
                "available": row["available"],
                "critical_recall": row.get("critical_evidence_recall_at_4"),
                "answerable_recall": (row.get("metrics") or {}).get("answerable_evidence_recall_at_k"),
                "ndcg": (row.get("metrics") or {}).get("ndcg_at_k"),
                "reason": row.get("reason"),
            }
            for row in development
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
