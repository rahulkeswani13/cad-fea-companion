from __future__ import annotations

import numpy as np

from companion.rag.chunking import Chunk
from companion.rag.neural import NeuralModels, NeuralRetriever, rewrite_query
from companion.rag.store import LocalTfidfStore


class FakeEmbedder:
    def encode(self, texts, **kwargs):
        vectors = []
        for text in texts:
            lower = text.lower()
            vectors.append([
                float("titanium" in lower or "ti-6al" in lower),
                float("mesh" in lower),
                float("aluminum" in lower),
            ])
        arr = np.asarray(vectors, dtype=float)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / np.where(norms == 0, 1, norms)


class FakeReranker:
    def predict(self, pairs, **kwargs):
        return np.asarray([10.0 if "880 MPa" in passage else 0.0 for _, passage in pairs])


def store(tmp_path, monkeypatch):
    from companion.config import get_settings

    monkeypatch.setattr(get_settings(), "vectorstore_dir", tmp_path)
    result = LocalTfidfStore()
    result.add_chunks([
        Chunk("a", "a.md", "aluminum reference value", section_id="a.md::s"),
        Chunk("b", "b.md", "Ti-6Al-4V titanium yield is 880 MPa", section_id="b.md::s"),
        Chunk("c", "c.md", "mesh convergence uses several sizes", section_id="c.md::s"),
    ])
    result.build(persist=False)
    return result


def test_embedding_profile_adds_rank_metadata(tmp_path, monkeypatch):
    retriever = NeuralRetriever(store(tmp_path, monkeypatch), NeuralModels(FakeEmbedder()))
    detail = retriever.search_detail("titanium", profile="lexical_embedding", k=2)
    assert detail["retrieval"]["available"] is True
    assert detail["retrieval"]["active_profile"] == "lexical_embedding"
    assert detail["fused"][0]["embedding_rank"] == 1
    assert "embedding" in detail["fused"][0]["methods"]


def test_reranker_reorders_candidate_union(tmp_path, monkeypatch):
    models = NeuralModels(FakeEmbedder(), FakeReranker())
    detail = NeuralRetriever(store(tmp_path, monkeypatch), models).search_detail(
        "material strength", profile="reranked", k=2
    )
    assert detail["fused"][0]["source"] == "b.md"
    assert detail["fused"][0]["rerank_score"] == 10.0
    assert "cross_encoder" in detail["fused"][0]["methods"]


def test_deterministic_query_rewrite_is_visible_and_label_independent(tmp_path, monkeypatch):
    query = "What are the default cantilever demo beam dimensions?"
    rewritten, rules = rewrite_query(query)
    assert rewritten.startswith(query)
    assert rules == ["cantilever_default_dimensions"]
    assert all(term in rewritten for term in ("length", "width", "height"))
    assert "100 mm" not in rewritten and "20 mm" not in rewritten and "5 mm" not in rewritten
    assert "mat-016" not in rewritten

    detail = NeuralRetriever(
        store(tmp_path, monkeypatch), NeuralModels(FakeEmbedder())
    ).search_detail(query, profile="lexical_embedding", k=2)
    assert detail["retrieval"]["query_rewrite"]["applied"] is True
    assert detail["retrieval"]["query_rewrite"]["rules"] == rules


def test_lexical_profile_preserves_original_query_behavior(tmp_path, monkeypatch):
    detail = NeuralRetriever(store(tmp_path, monkeypatch)).search_detail(
        "What are the default cantilever demo beam dimensions?",
        profile="lexical",
        k=2,
    )
    assert detail["retrieval"]["query_rewrite"] == {"applied": False, "rules": []}


def test_missing_models_fall_back_visibly_or_mark_unavailable(tmp_path, monkeypatch):
    retriever = NeuralRetriever(store(tmp_path, monkeypatch))
    monkeypatch.setattr("companion.rag.neural.load_models", lambda *a, **k: (_ for _ in ()).throw(ImportError("missing")))
    fallback = retriever.search_detail("mesh", profile="reranked", k=2)
    assert fallback["retrieval"]["fallback"] is True
    assert fallback["retrieval"]["active_profile"] == "lexical"
    assert fallback["retrieval"]["query_rewrite"]["applied"] is False
    assert fallback["fused"]
    strict = retriever.search_detail("mesh", profile="reranked", k=2, strict=True)
    assert strict["retrieval"]["active_profile"] == "unavailable"
    assert strict["fused"] == []


def test_invalid_profile_is_rejected(tmp_path, monkeypatch):
    retriever = NeuralRetriever(store(tmp_path, monkeypatch))
    try:
        retriever.search_detail("mesh", profile="magic")
    except ValueError as exc:
        assert "profile must be one of" in str(exc)
    else:
        raise AssertionError("invalid profile should fail")
