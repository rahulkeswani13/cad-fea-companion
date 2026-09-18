#!/usr/bin/env python3
"""Validate and run the independently authored RAG hidden-v2 evaluation once."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from companion.rag.chunking import Chunk, chunk_text  # noqa: E402
from companion.rag.corpus import manifest_entries  # noqa: E402
from companion.rag.store import (  # noqa: E402
    LocalTfidfStore,
    collect_corpus_files,
    corpus_fingerprint,
)

FIXTURE_PATH = ROOT / "eval" / "rag_hidden_v2.json"
EXPECTED_CASES = 30
FINAL_K = 4
MIN_ANSWERABLE_GAIN = 0.05
MAX_RERANKED_MEDIAN_MS = 500.0
RETRIEVER_SOURCES = (
    ROOT / "companion" / "rag" / "chunking.py",
    ROOT / "companion" / "rag" / "neural.py",
    ROOT / "companion" / "rag" / "store.py",
)


class HiddenEvaluationError(ValueError):
    """The hidden fixture or frozen implementation no longer matches."""


def retriever_fingerprint(paths: tuple[Path, ...] = RETRIEVER_SOURCES) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        label = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_current_corpus() -> tuple[LocalTfidfStore, str]:
    """Build the reviewed corpus in memory without replacing the accepted index."""
    metadata = {item["path"]: item for item in manifest_entries()}
    store = LocalTfidfStore()
    documents: list[dict[str, Any]] = []
    for path, source in collect_corpus_files():
        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(text, source=source)
        for chunk in chunks:
            chunk.metadata.update(metadata.get(source, {}))
        store.add_chunks(chunks)
        documents.append(
            {
                "path": source,
                "chunks": len(chunks),
                "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "metadata": metadata.get(source, {}),
            }
        )
    store.index_metadata = {"fingerprint": corpus_fingerprint(documents)}
    store.build(persist=False)
    return store, store.index_metadata["fingerprint"]


def _evidence_matches(chunk: Chunk | dict[str, Any], evidence: dict[str, str]) -> bool:
    getter = chunk.get if isinstance(chunk, dict) else lambda key, default=None: getattr(chunk, key, default)
    return (
        getter("source") == evidence["source"]
        and getter("section_id") == evidence["section_id"]
        and evidence["quote"] in str(getter("text", ""))
    )


def resolve_evidence(
    case: dict[str, Any], chunks: list[Chunk]
) -> list[list[set[str]]]:
    resolved: list[list[set[str]]] = []
    for group in case["evidence_groups"]:
        resolved_group: list[set[str]] = []
        for evidence in group["evidence"]:
            matches = {chunk.chunk_id for chunk in chunks if _evidence_matches(chunk, evidence)}
            if not matches:
                raise HiddenEvaluationError(
                    f"{case['id']}: unresolved evidence {evidence['source']} "
                    f"{evidence['section_id']} quote={evidence['quote']!r}"
                )
            resolved_group.append(matches)
        resolved.append(resolved_group)
    return resolved


def validate_fixture(
    fixture: dict[str, Any],
    chunks: list[Chunk],
    *,
    current_corpus_fingerprint: str,
    current_retriever_fingerprint: str,
) -> dict[str, list[list[set[str]]]]:
    metadata = fixture.get("metadata") or {}
    cases = fixture.get("cases")
    if fixture.get("schema_version") != 2 or not isinstance(cases, list):
        raise HiddenEvaluationError("hidden-v2 requires schema_version 2 and a cases list")
    if len(cases) != EXPECTED_CASES or metadata.get("case_count") != EXPECTED_CASES:
        raise HiddenEvaluationError(f"hidden-v2 must contain exactly {EXPECTED_CASES} cases")
    if metadata.get("final_k") != FINAL_K or metadata.get("selected_profile") != "reranked":
        raise HiddenEvaluationError("hidden-v2 must bind reranked retrieval at final k=4")
    if metadata.get("corpus_fingerprint") != current_corpus_fingerprint:
        raise HiddenEvaluationError("Corpus drift: hidden-v2 evidence no longer matches the frozen corpus")
    if metadata.get("retriever_fingerprint") != current_retriever_fingerprint:
        raise HiddenEvaluationError("Retriever drift: hidden-v2 may only run against the frozen retriever")

    seen: set[str] = set()
    resolved: dict[str, list[list[set[str]]]] = {}
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise HiddenEvaluationError("case ids must be non-empty and unique")
        seen.add(case_id)
        if case.get("expected_behavior") not in {"answer", "clarify", "refuse"}:
            raise HiddenEvaluationError(f"{case_id}: invalid expected_behavior")
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            raise HiddenEvaluationError(f"{case_id}: query is required")
        if not isinstance(case.get("history"), list):
            raise HiddenEvaluationError(f"{case_id}: history must be a list")
        for turn in case["history"]:
            if (
                not isinstance(turn, dict)
                or set(turn) != {"role", "content"}
                or turn["role"] not in {"user", "assistant"}
                or not isinstance(turn["content"], str)
                or not turn["content"].strip()
            ):
                raise HiddenEvaluationError(f"{case_id}: malformed history turn")
        if not isinstance(case.get("critical"), bool):
            raise HiddenEvaluationError(f"{case_id}: critical must be boolean")
        for field in ("required_facts", "forbidden_claims", "numeric_expectations"):
            if not isinstance(case.get(field), list):
                raise HiddenEvaluationError(f"{case_id}: {field} must be a list")
        groups = case.get("evidence_groups")
        if not isinstance(groups, list) or not groups:
            raise HiddenEvaluationError(f"{case_id}: at least one evidence group is required")
        group_ids: set[str] = set()
        for group in groups:
            group_id = group.get("group_id")
            evidence = group.get("evidence")
            if not isinstance(group_id, str) or not group_id or group_id in group_ids:
                raise HiddenEvaluationError(f"{case_id}: evidence group ids must be unique")
            group_ids.add(group_id)
            if not isinstance(evidence, list) or not evidence:
                raise HiddenEvaluationError(f"{case_id}/{group_id}: evidence is required")
            for item in evidence:
                if set(item) != {"source", "section_id", "quote"}:
                    raise HiddenEvaluationError(f"{case_id}/{group_id}: malformed evidence item")
                if not item["source"].startswith("docs/reference/"):
                    raise HiddenEvaluationError(f"{case_id}/{group_id}: source is outside docs/reference")
                if not item["section_id"].startswith(f"{item['source']}::"):
                    raise HiddenEvaluationError(f"{case_id}/{group_id}: section does not belong to source")
        resolved[case_id] = resolve_evidence(case, chunks)
    return resolved


def _ndcg(binary_relevance: list[int], relevant_count: int, k: int) -> float:
    dcg = sum(rel / math.log2(rank + 2) for rank, rel in enumerate(binary_relevance[:k]))
    ideal_count = min(k, relevant_count)
    idcg = sum(1.0 / math.log2(rank + 2) for rank in range(ideal_count))
    return dcg / idcg if idcg else 0.0


def _retrieval_query(case: dict[str, Any]) -> str:
    """Render only supplied conversation context; never infer hidden facts."""
    turns = [
        f"{turn['role']}: {turn['content']}"
        for turn in case["history"]
        if isinstance(turn, dict) and turn.get("role") in {"user", "assistant"}
        and isinstance(turn.get("content"), str) and turn["content"].strip()
    ]
    turns.append(f"user: {case['query']}")
    return "\n".join(turns)


def evaluate_cases(
    cases: list[dict[str, Any]],
    resolved: dict[str, list[list[set[str]]]],
    retrieve_fn: Callable[[str, int], list[dict[str, Any]]],
    *,
    k: int = FINAL_K,
) -> dict[str, Any]:
    """Call retrieval exactly once per case and calculate evidence-level metrics."""
    rows: list[dict[str, Any]] = []
    timings: list[float] = []
    for case in cases:
        retrieval_query = _retrieval_query(case)
        started = perf_counter()
        hits = (retrieve_fn(retrieval_query, k) or [])[:k]
        timings.append((perf_counter() - started) * 1000.0)
        hit_ids = [str(hit.get("chunk_id") or "") for hit in hits]
        groups = resolved[case["id"]]
        group_hits = [all(bool(options.intersection(hit_ids)) for options in group) for group in groups]
        recall = sum(group_hits) / len(group_hits)
        relevant_ids = set().union(*(options for group in groups for options in group))
        binary = [int(chunk_id in relevant_ids) for chunk_id in hit_ids]
        precision = sum(binary) / k if k else 0.0
        ndcg = _ndcg(binary, len(relevant_ids), k)
        rows.append(
            {
                "id": case["id"],
                "expected_behavior": case["expected_behavior"],
                "critical": case["critical"],
                "retrieval_query": retrieval_query,
                "evidence_groups_recalled": sum(group_hits),
                "evidence_groups_total": len(group_hits),
                "evidence_recall_at_k": round(recall, 4),
                "evidence_precision_at_k": round(precision, 4),
                "ndcg_at_k": round(ndcg, 4),
                "ranked_chunk_ids": hit_ids,
            }
        )

    def mean(field: str, selected: list[dict[str, Any]]) -> float:
        return round(statistics.mean(float(row[field]) for row in selected), 4) if selected else 0.0

    answerable = [row for row in rows if row["expected_behavior"] == "answer"]
    critical = [row for row in rows if row["critical"]]
    ordered = sorted(timings)
    p95_index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))
    return {
        "queries": len(rows),
        "query_call_count": len(rows),
        "k": k,
        "evidence_recall_at_k": mean("evidence_recall_at_k", rows),
        "answerable_evidence_recall_at_k": mean("evidence_recall_at_k", answerable),
        "evidence_precision_at_k": mean("evidence_precision_at_k", rows),
        "ndcg_at_k": mean("ndcg_at_k", rows),
        "critical_evidence_recall_at_k": mean("evidence_recall_at_k", critical),
        "timing": {
            "median_query_ms": round(statistics.median(timings), 2),
            "mean_query_ms": round(statistics.mean(timings), 2),
            "p95_query_ms": round(ordered[p95_index], 2),
        },
        "per_query": rows,
    }


def experimental_gate(reranked: dict[str, Any], lexical: dict[str, Any]) -> dict[str, Any]:
    gain = float(reranked["answerable_evidence_recall_at_k"]) - float(
        lexical["answerable_evidence_recall_at_k"]
    )
    checks = {
        "answerable_gain_at_least_0_05": gain >= MIN_ANSWERABLE_GAIN,
        "ndcg_improved": float(reranked["ndcg_at_k"]) > float(lexical["ndcg_at_k"]),
        "critical_not_regressed": float(reranked["critical_evidence_recall_at_k"])
        >= float(lexical["critical_evidence_recall_at_k"]),
        "reranked_median_below_500_ms": float(reranked["timing"]["median_query_ms"])
        < MAX_RERANKED_MEDIAN_MS,
    }
    return {"passed": all(checks.values()), "answerable_gain": round(gain, 4), "checks": checks}


def run_hidden_evaluation(
    fixture: dict[str, Any],
    store: LocalTfidfStore,
    resolved: dict[str, list[list[set[str]]]],
    *,
    allow_download: bool,
) -> dict[str, Any]:
    cases = fixture["cases"]
    lexical = evaluate_cases(cases, resolved, lambda query, k: store.search(query, k=k))

    load_started = perf_counter()
    try:
        from companion.rag.neural import NeuralRetriever, load_models

        models = load_models("reranked", local_files_only=not allow_download)
    except Exception as exc:  # availability remains explicit; never score lexical as reranked
        reranked = {
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "model_load_ms": round((perf_counter() - load_started) * 1000.0, 2),
            "query_call_count": 0,
        }
        gate = {"passed": False, "reason": "reranked_unavailable"}
    else:
        load_ms = (perf_counter() - load_started) * 1000.0
        retriever = NeuralRetriever(store, models)

        def retrieve_reranked(query: str, k: int) -> list[dict[str, Any]]:
            detail = retriever.search_detail(query, profile="reranked", k=k, strict=True)
            status = detail["retrieval"]
            if status.get("active_profile") != "reranked":
                raise HiddenEvaluationError(status.get("reason") or "reranked profile unavailable")
            return detail["fused"]

        reranked = evaluate_cases(cases, resolved, retrieve_reranked)
        reranked["model_load_ms"] = round(load_ms, 2)
        reranked["available"] = True
        gate = experimental_gate(reranked, lexical)

    return {
        "schema_version": 2,
        "fixture_id": fixture["metadata"]["fixture_id"],
        "corpus_fingerprint": fixture["metadata"]["corpus_fingerprint"],
        "retriever_fingerprint": fixture["metadata"]["retriever_fingerprint"],
        "configuration": {
            "profiles": ["lexical", "reranked"],
            "final_k": FINAL_K,
            "evaluation_passes_per_profile": 1,
            "metric_definitions": {
                "recall": "mean fraction of required evidence groups recalled in top-k",
                "precision": "mean relevant retrieved chunks divided by k",
                "ndcg": "mean binary chunk-relevance nDCG at k",
                "critical_recall": "mean evidence-group recall over critical cases",
            },
        },
        "profiles": {"lexical": {"available": True, **lexical}, "reranked": reranked},
        "experimental_gate": gate,
        "historical_heldout": {"status": "unsupported_not_run", "run_count": 0},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download-models", action="store_true")
    args = parser.parse_args()

    if args.output.exists():
        parser.error(
            f"refusing to overwrite existing hidden-v2 report: {args.output}"
        )

    fixture = load_fixture()
    store, current_corpus = build_current_corpus()
    current_retriever = retriever_fingerprint()
    resolved = validate_fixture(
        fixture,
        store.chunks,
        current_corpus_fingerprint=current_corpus,
        current_retriever_fingerprint=current_retriever,
    )
    report = run_hidden_evaluation(
        fixture, store, resolved, allow_download=args.download_models
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "experimental_gate": report["experimental_gate"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
