"""RAG ingest: curated allowlist corpus (ADR-014, fails closed)."""

from __future__ import annotations

from companion.config import Settings
from companion.rag.store import (
    Chunk,
    LocalTfidfStore,
    collect_corpus_files,
    corpus_fingerprint,
    grounding_label,
    ingest_docs,
    rrf_fuse,
)


def test_ingest_defaults_to_declared_corpus_dirs():
    result = ingest_docs()
    assert result["ok"] is True
    paths = [doc["path"] for doc in result["documents"]]
    assert len(paths) == 20
    assert all(p.startswith(("docs/reference/", "docs/adr/")) for p in paths)
    assert "docs/reference/ARCHITECTURE.md" in paths
    assert "docs/reference/materials.md" in paths
    assert not any("PLAN" in p for p in paths)


def test_ingest_is_fail_closed_outside_declared_dirs(tmp_path):
    corpus = tmp_path / "reference"
    corpus.mkdir()
    (corpus / "kept.md").write_text("# kept\n\nmesh convergence notes", encoding="utf-8")
    (tmp_path / "stray.md").write_text("# stray\n\nmust never be ingested", encoding="utf-8")
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / "roadmap.md").write_text("# roadmap\n\nintentions, not corpus", encoding="utf-8")

    # Pure selection: no global store or persisted index touched.
    selected = collect_corpus_files([corpus])
    assert selected == [(corpus / "kept.md", str(corpus / "kept.md"))]


def test_ingest_missing_corpus_dir_is_empty_not_error(tmp_path):
    assert collect_corpus_files([tmp_path / "nope"]) == []


def test_rag_corpus_dirs_accepts_comma_separated_env():
    settings = Settings(_env_file=None, rag_corpus_dirs="docs/reference, docs/adr")
    assert settings.rag_corpus_dirs == ["docs/reference", "docs/adr"]


def test_corpus_fingerprint_is_order_and_doc_set_sensitive():
    a = [{"path": "docs/reference/a.md", "chunks": 3}, {"path": "docs/adr/x.md", "chunks": 1}]
    b = [{"path": "docs/adr/x.md", "chunks": 1}, {"path": "docs/reference/a.md", "chunks": 3}]
    assert corpus_fingerprint(a) == corpus_fingerprint(b)  # order-independent
    moved = [{"path": "docs/reference/a.md", "chunks": 3}, {"path": "docs/adr/x.md", "chunks": 2}]
    assert corpus_fingerprint(a) != corpus_fingerprint(moved)  # chunk drift shows
    grown = a + [{"path": "docs/reference/new.md", "chunks": 4}]
    assert corpus_fingerprint(a) != corpus_fingerprint(grown)  # doc drift shows


# --- Hybrid retrieval (ADR-012) -------------------------------------------


def _synthetic_store() -> LocalTfidfStore:
    store = LocalTfidfStore()
    store.add_chunks(
        [
            Chunk("a::0", "docs/a.md", "aluminum 6061-T6 yield strength is 276 MPa"),
            Chunk("b::0", "docs/b.md", "titanium Ti-6Al-4V yield strength is 880 MPa"),
            Chunk("c::0", "docs/c.md", "the strut radius floor keeps lattice cells meshable"),
            Chunk("d::0", "docs/d.md", "mesh convergence study sweeps three mesh sizes"),
        ]
    )
    store.build()
    return store


def test_rrf_fuse_interleaves_disagreeing_rankers():
    # TF-IDF order: 10, 20, 30 · BM25 order: 20, 30, 40. RRF (k=60):
    # 20 -> 1/62+1/61, 30 -> 1/63+1/62, 10 -> 1/61, 40 -> 1/63.
    fused = rrf_fuse({10: 1, 20: 2, 30: 3}, {20: 1, 30: 2, 40: 3})
    assert [idx for idx, _ in fused] == [20, 30, 10, 40]
    # Double-ranked docs beat single-ranked docs of one rank better.
    scores = dict(fused)
    assert scores[20] > scores[30] > scores[10] > scores[40]


def test_grounding_label_paths():
    strong_hit = {"score": 0.5, "bm25_rank": 1}
    weak_hit = {"score": 0.01, "bm25_rank": 8}
    rescued_hit = {"score": 0.01, "bm25_rank": 1}
    assert grounding_label([], 0.05, 3) == "none"
    assert grounding_label([strong_hit], 0.05, 3) == "strong"
    assert grounding_label([weak_hit], 0.05, 3) == "weak"
    # BM25 rescue: low cosine but a top-BM25 hit is still confident.
    assert grounding_label([rescued_hit], 0.05, 3) == "strong"
    # Malformed/missing ranks degrade to the cosine check only.
    assert grounding_label([{"score": 0.01, "bm25_rank": None}], 0.05, 3) == "weak"


def test_hybrid_hits_keep_legacy_shape_and_add_rank_fields():
    store = _synthetic_store()
    hits = store.search("titanium yield strength", k=3)
    assert hits, "expected hits for a corpus-matching query"
    legacy_keys = {"chunk_id", "source", "text", "score"}
    new_keys = {
        "methods",
        "tfidf_rank",
        "bm25_rank",
        "bm25_score",
        "fused_rank",
        "rrf_score",
    }
    for pos, hit in enumerate(hits, start=1):
        assert legacy_keys | new_keys <= set(hit)
        assert hit["fused_rank"] == pos
        assert hit["methods"], "every fused hit must come from some retriever"
        assert hit["rrf_score"] > 0
    assert hits[0]["fused_rank"] == 1


def test_store_stats_counts_synthetic_corpus():
    store = _synthetic_store()
    stats = store.stats()
    assert stats["ok"] is True
    assert stats["docs"] == 4
    assert stats["chunks"] == 4
    assert stats["avg_chunk_chars"] > 0
    assert stats["retrievers"] == ["tfidf", "bm25"]
    by_path = {s["path"]: s["chunks"] for s in stats["sources"]}
    assert by_path == {
        "docs/a.md": 1,
        "docs/b.md": 1,
        "docs/c.md": 1,
        "docs/d.md": 1,
    }
