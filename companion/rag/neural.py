"""Optional local embedding retrieval and cross-encoder reranking (ADR-018).

The legacy lexical store remains the guaranteed path. Neural profiles load only
from pinned local model revisions unless an experiment explicitly provisions
them. Runtime failures return a visible lexical fallback; strict experiments
return ``unavailable`` so a fallback cannot be reported as a neural result.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter
from typing import Any

import numpy as np

from companion.rag.store import _CANDIDATES, _RRF_K, LocalTfidfStore

EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
RERANKER_MODEL_ID = "cross-encoder/ms-marco-MiniLM-L6-v2"
RERANKER_MODEL_REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
PROFILES = ("lexical", "lexical_embedding", "reranked")


@dataclass
class NeuralModels:
    embedder: Any
    reranker: Any | None = None


@lru_cache(maxsize=4)
def load_models(profile: str, *, local_files_only: bool = True) -> NeuralModels:
    """Load the exact approved revisions, optionally allowing provisioning."""
    if profile not in PROFILES[1:]:
        raise ValueError(f"Neural models are not used by profile {profile!r}")
    from sentence_transformers import CrossEncoder, SentenceTransformer

    embedder = SentenceTransformer(
        EMBEDDING_MODEL_ID,
        revision=EMBEDDING_MODEL_REVISION,
        local_files_only=local_files_only,
    )
    reranker = None
    if profile == "reranked":
        reranker = CrossEncoder(
            RERANKER_MODEL_ID,
            revision=RERANKER_MODEL_REVISION,
            local_files_only=local_files_only,
        )
    return NeuralModels(embedder=embedder, reranker=reranker)


def _fuse_many(*rankings: dict[int, int]) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for idx, rank in ranking.items():
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (_RRF_K + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


class NeuralRetriever:
    """Compare fixed lexical, embedding-union, and reranked profiles."""

    def __init__(self, store: LocalTfidfStore, models: NeuralModels | None = None):
        self.store = store
        self.models = models
        self._corpus_embeddings: np.ndarray | None = None

    def _ensure_embeddings(self) -> np.ndarray:
        if self.models is None:
            raise RuntimeError("neural models are unavailable")
        if self._corpus_embeddings is None:
            self._corpus_embeddings = np.asarray(
                self.models.embedder.encode(
                    [chunk.text for chunk in self.store.chunks],
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                ),
                dtype=float,
            )
        return self._corpus_embeddings

    def _status(self, requested: str, active: str, start: float, **extra: Any) -> dict[str, Any]:
        return {
            "requested_profile": requested,
            "active_profile": active,
            "available": requested == active,
            "fallback": requested != active,
            "grounding_basis": "lexical_top_hit",
            "timing_ms": round((perf_counter() - start) * 1000.0, 2),
            "models": {
                "embedding": {"id": EMBEDDING_MODEL_ID, "revision": EMBEDDING_MODEL_REVISION},
                "reranker": {"id": RERANKER_MODEL_ID, "revision": RERANKER_MODEL_REVISION}
                if requested == "reranked" else None,
            },
            **extra,
        }

    def search_detail(self, query: str, *, profile: str, k: int = 4, strict: bool = False) -> dict[str, Any]:
        if profile not in PROFILES:
            raise ValueError(f"profile must be one of {PROFILES}, got {profile!r}")
        start = perf_counter()
        lexical = self.store.search_detail(query, k=k)
        if profile == "lexical":
            return {**lexical, "retrieval": self._status(profile, profile, start)}
        try:
            if self.models is None:
                self.models = load_models(profile, local_files_only=True)
            if profile == "reranked" and self.models.reranker is None:
                raise RuntimeError("cross-encoder reranker is unavailable")
            tfidf_rank, bm25_rank, cos, bm25_scores = self.store._rankings(query)
            corpus = self._ensure_embeddings()
            query_vector = np.asarray(
                self.models.embedder.encode(
                    [query], normalize_embeddings=True, convert_to_numpy=True,
                    show_progress_bar=False,
                ),
                dtype=float,
            )[0]
            embedding_scores = corpus @ query_vector
            embedding_order = np.argsort(-embedding_scores)[:_CANDIDATES]
            embedding_rank = {int(idx): rank + 1 for rank, idx in enumerate(embedding_order)}
            union = _fuse_many(tfidf_rank, bm25_rank, embedding_rank)
            rerank_scores: dict[int, float] = {}
            if profile == "reranked":
                candidate_ids = [idx for idx, _ in union]
                predicted = self.models.reranker.predict(
                    [(query, self.store.chunks[idx].text) for idx in candidate_ids],
                    show_progress_bar=False,
                )
                rerank_scores = {idx: float(score) for idx, score in zip(candidate_ids, predicted)}
                ordered = sorted(candidate_ids, key=lambda idx: (-rerank_scores[idx], idx))
            else:
                ordered = [idx for idx, _ in union]
            rrf_scores = dict(union)
            hits = []
            for rank, idx in enumerate(ordered[:k], 1):
                hit = self.store._hit(
                    idx, cos, bm25_scores, tfidf_rank, bm25_rank,
                    fused_rank=rank, rrf_score=rrf_scores.get(idx),
                )
                if idx in embedding_rank:
                    hit["methods"].append("embedding")
                if profile == "reranked":
                    hit["methods"].append("cross_encoder")
                hit.update({
                    "embedding_rank": embedding_rank.get(idx),
                    "embedding_score": round(float(embedding_scores[idx]), 6),
                    "rerank_score": round(rerank_scores[idx], 6) if idx in rerank_scores else None,
                    "retrieval_profile": profile,
                })
                hits.append(hit)
            return {
                **lexical,
                "fused": hits,
                "embedding": [
                    {"chunk_id": self.store.chunks[idx].chunk_id,
                     "source": self.store.chunks[idx].source,
                     "section_id": self.store.chunks[idx].section_id,
                     "text": self.store.chunks[idx].text,
                     "embedding_rank": embedding_rank[idx],
                     "embedding_score": round(float(embedding_scores[idx]), 6)}
                    for idx in embedding_order
                ],
                "retrieval": self._status(profile, profile, start),
            }
        except Exception as exc:  # model boundary: lexical remains usable
            status = self._status(
                profile,
                "unavailable" if strict else "lexical",
                start,
                reason=f"{type(exc).__name__}: {exc}",
            )
            if strict:
                return {"grounding": "none", "tfidf": [], "bm25": [], "embedding": [],
                        "fused": [], "retrieval": status}
            return {**lexical, "embedding": [], "retrieval": status}


def retrieve_profile_detail(
    query: str,
    *,
    profile: str,
    k: int = 4,
    strict: bool = False,
    allow_download: bool = False,
    store: LocalTfidfStore | None = None,
) -> dict[str, Any]:
    from companion.rag.store import get_store

    target = store or get_store()
    models = None
    if profile != "lexical" and allow_download:
        try:
            models = load_models(profile, local_files_only=False)
        except Exception:
            models = None
    return NeuralRetriever(target, models).search_detail(query, profile=profile, k=k, strict=strict)
