# ADR-012: Hybrid retrieval (TF-IDF + BM25, RRF) with a grounding label

Status: accepted — 2026-09-01

## Context

Retrieval was a bare TF-IDF cosine over ~120 chunks. Three pressures forced a
decision:

1. **Quality.** TF-IDF vocabulary oversampling misranks identifier-style
   queries ("ti64", "ADR-009") that BM25's saturation + length normalization
   handle well. Fusion fixes the common failure mode without any model.
2. **Honesty parity.** Solves carry method labels and not-verified flags
   (ADR-007), but retrieval quality was invisible — the UI dressed up
   low-confidence hits as if they were grounded. Retrieval needs the same
   treatment.
3. **Constraints.** Zero API tokens, zero model downloads, offline-first demo
   resilience. F15 (embedding RAG) stays on the roadmap; this is its
   algorithmic precursor, not a replacement.

## Decision

1. **Hybrid, algorithmic only.** BM25 (BM25Okapi via `rank_bm25`, the only new
   dependency) runs alongside TF-IDF over the same chunks. Tokenization is
   shared: BM25 consumes `vectorizer.build_analyzer()` output, so the two
   retrievers can never drift apart on preprocessing.
2. **Rank fusion, not score fusion.** Reciprocal Rank Fusion with the standard
   k=60 damping (`rrf_fuse`), over each retriever's top-10 candidates. RRF
   needs no cross-retriever score normalization and is insensitive to score
   scale differences.
3. **Grounding label, backend-only.** `retrieve_detail()` returns
   `grounding: strong | weak | none` computed from the fused top hit: `strong`
   when TF-IDF cosine ≥ `RAG_GROUNDING_MIN_TFIDF` (default 0.05) **or** the hit
   sits in the BM25 top-`RAG_GROUNDING_BM25_TOP` (default 3); `weak` otherwise;
   `none` when nothing matched. The label is one source of truth consumed by
   the chat UI and the RAG Lab; it is an annotation, never a filter — weak
   hits still flow (solver-honesty style: state, don't hide).
4. **Back-compat is a hard rule.** `retrieve(query, k)` keeps its signature and
   list shape; hits keep `chunk_id` / `source` / `text` / `score` (still the
   TF-IDF cosine). Rank fields (`methods`, `tfidf_rank`, `bm25_rank`,
   `bm25_score`, `fused_rank`, `rrf_score`) are additive. `/api/rag/search`
   gains an optional `detail=1` breakdown; `/api/rag/stats` is new.
5. **Pluggable rerank seam, no reranker.** No cross-encoder or embeddings this
   round (they need model downloads / tokens). `rrf_fuse` + the detail shape
   give a local cross-encoder a drop-in seam later without touching call
   sites.
6. **Chunking frozen.** `chunk_text` is untouched this round so the 8 RAG eval
   cases stay valid without re-tuning; chunking overlap is a deliberate
   follow-up.
7. **New optional env keys** (`.env.example` documented, defaults in
   `config.py`): `RAG_GROUNDING_MIN_TFIDF`, `RAG_GROUNDING_BM25_TOP`.

## Consequences

- Chat answers and the RAG Lab surface *why* a chunk was retrieved (which
  retriever, which rank) — retrieval becomes inspectable, demoable, and
  honest about weak grounding.
- The 8 RAG eval cases pass untouched (chunking frozen, score key stable).
- F15 later adds embeddings behind the same seam; `grounding` may then be
  calibrated on the same thresholds or replaced by a learned one.
