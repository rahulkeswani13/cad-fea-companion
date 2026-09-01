# RAG Upgrade Plan — Hybrid Retrieval + RAG Lab UI (3.5 → ~6)

**Status:** Planned (grilled & settled 2026-09-01) · **Effort:** ~1 day · **Cost:** zero API tokens

## Goal

Lift retrieval quality from bare TF-IDF to hybrid TF-IDF + BM25 with Reciprocal Rank
Fusion (RRF), make grounding quality *visible* in the UI, and produce one quotable
number and three demo-ready props for interviews.

## Constraints (settled decisions — do not reopen)

| Decision | Choice |
| :--- | :--- |
| Reranker / embeddings | **Excluded.** Pure algorithmic only. Store keeps a pluggable rerank hook (`rerank_fn=None`) so a cross-encoder can drop in later without touching call sites. |
| Chunking | **Frozen.** `chunk_text` untouched → the 8 existing RAG eval cases stay valid with no re-tuning. |
| Weak-grounding logic | **Backend-only.** `retrieve()` returns an additive `grounding: "strong" \| "weak"` label; thresholds live in `config.py` with `.env` overrides. Calibrated once by eyeball on ~5 sample queries. |
| Tests | **Minimal**: unit tests for new pure functions only (fusion, grounding label, stats payload). Run once. No browser-suite re-runs, no eval re-tuning. |
| Build order | **Core first** (morning), UI second (afternoon). |
| Scope exclusions | No CAD/geometry/solver changes, no LLM calls, no CI work, no new parts or workflows. |

---

## Phase 1 — Core retrieval (morning, ~3.5 h)

### 1.1 BM25 index (`companion/rag/store.py`)

- Build a BM25 index alongside the existing TF-IDF matrix in `build()` / `load()`.
  In-memory only; rebuilt from `self.chunks` — **no new persisted artifacts**.
- Tokenization: reuse `self.vectorizer.build_analyzer()` so BM25 sees exactly the same
  tokens TF-IDF sees (prevents a tokenization-mismatch bug class).
- Dependency: `rank_bm25` (pure Python, no transitive deps) added to `requirements.txt`.
  *Fallback if a zero-new-deps stance is preferred:* ~40-line inline BM25Okapi — same
  interface. Pick one; do not hand-roll *and* ship the dep.

### 1.2 Hybrid search with RRF

- `search()` runs both retrievers → top-N each (N=10) → RRF fuse with k=60 → return top-k.
- **Back-compat is a hard rule (AGENTS.md #1):** every hit keeps `chunk_id`, `source`,
  `text`, `score` (TF-IDF cosine) byte-compatible. Additive fields per hit:
  - `methods: ["tfidf", "bm25"]` — which retriever(s) surfaced it
  - `tfidf_rank`, `bm25_rank`, `fused_rank` (ints or null)
  - `bm25_score` (float or null)
- Response gains top-level `grounding: "strong" | "weak" | "none"`.

### 1.3 Grounding label

- Rule (simple, defensible, calibrate-once): `weak` when the fused top hit has
  TF-IDF cosine below `RAG_GROUNDING_MIN_TFIDF` **and** no BM25 top-3 presence;
  `none` when zero hits. Constants in `config.py` (`Settings`), optional `.env`
  overrides documented in `.env.example` (note the new keys in ADR-012 per AGENTS.md #7).
- Calibration: one pass over 5 queries (3 corpus-friendly, 2 nonsense) — done once
  during Phase 1, not an eval suite.

### 1.4 API (additive only, `companion/main.py`)

- `GET /api/rag/search` — existing params unchanged; response shape extended as above.
- `GET /api/rag/stats` — **new**: `{docs, chunks, avg_chunk_chars, sources: [{path, chunks}], index_updated_at, retrievers}`.
  `index_updated_at` = mtime of `tfidf_store.json`; `docs/chunks` from the live store.
- `/api/chat` and `/api/chat/stream` final payloads — add top-level `grounding`
  alongside `citations` (additive; existing UI keys untouched).

### 1.5 Unit tests (`tests/test_rag.py` additions — run once)

1. **Fusion ordering:** 2-doc corpus where TF-IDF ranks A top and BM25 ranks B top →
   RRF interleaves per the k=60 math.
2. **Grounding:** empty store → `none`; below-threshold scores → `weak`; good hit → `strong`.
3. **Stats:** counts and per-source breakdown match a known corpus.
4. **Back-compat:** hit dict is a superset of the old shape (old keys present).

---

## Phase 2 — UI (afternoon, ~3.5 h)

### 2.1 Chat page (`companion/static/index.html` — surgical edits only)

- **Citation chips** replace the plain deduped source list (currently
  `index.html:438-442`): one chip per source, click → expand the **Retrieval
  Inspector** under the answer — per hit: source path, chunk text (truncated,
  click-to-expand), TF-IDF/BM25 ranks, fused rank, scores, and which retriever(s) surfaced it.
- **Honesty badge:** `grounding == "weak"` → amber chip *"Weak grounding — the corpus
  has no strong match for this question"* above the sources; `strong` → quiet green dot;
  `none` → chip says the index returned nothing. Keep the existing inline
  citation-bracket stripping (`index.html:325`) unchanged.
- No framework, no build step — same vanilla JS/fetch patterns already in the file.

### 2.2 RAG Lab (`companion/static/rag.html` — new page)

Linked from the chat header ("RAG Lab ↗"). Same vanilla style. Two views:

- **Playground** — the demo centerpiece:
  - Query box → three columns side-by-side: **TF-IDF top-10**, **BM25 top-10**,
    **Fused top-k**.
  - Each row: rank, source path, score, chunk snippet. Fused rows annotated with which
    retriever contributed (`tfidf_rank` / `bm25_rank` visible side-by-side).
  - Grounding badge mirrors the chat page (same backend label).
- **Corpus stats panel:**
  - Cards: docs, chunks, avg chunk size, index updated-at, active retrievers.
  - Per-source table (path, chunk count), sortable by count.
  - **Rebuild index** button → `POST /api/rag/ingest` → refresh stats live.

---

## Phase 3 — Docs & repo compliance (~0.5 h)

- **`docs/adr/ADR-012-hybrid-retrieval.md`** — records: why BM25+RRF, why no
  embeddings/reranker (offline-first, zero-token constraint), the pluggable rerank hook,
  the backend grounding-label policy, new `.env` keys, chunking deferral.
- **`demo/Features.md`** — F01 section gains: updated pitch line, demo prompts, and
  likely interview questions (why not embeddings? how does RRF work? what does the
  grounding label guarantee?).
- **`README.md`** — one honest line: "hybrid TF-IDF + BM25 retrieval (RRF-fused) with a
  grounding-confidence label" replaces the bare TF-IDF phrasing.
- **`.env.example`** — document `RAG_GROUNDING_*` keys.

## Final verification (once, ~2 min, zero tokens)

- `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_browser_ui.py` (new tests included).
- `GEMINI_API_KEY= .venv/bin/python eval/run_eval.py` — key unset on purpose so the 10
  agent cases run the heuristic path: zero tokens, and chunking was frozen so the 8 RAG
  cases must pass untouched (if any fails, the fusion change broke back-compat — fix, don't re-tune).

---

## Demo script beats (what the upgrade buys you on stage)

1. **Grounding, made visible:** ask a materials question in chat → open the inspector →
   "here is the exact chunk, and here is how each retriever ranked it."
2. **Honesty:** ask for "the tensile strength of unobtainium" → amber weak-grounding
   badge + an honest "I don't know" answer — same philosophy as solver honesty, now on the retrieval side.
3. **The win, shown not claimed:** in RAG Lab, run an identifier-style query (e.g.
   "ti64" or "ADR-009") → TF-IDF misses or misranks, BM25 rescues it, fusion wins.
4. **Living system:** stats panel → rebuild index live → chunk count updates on screen.

## Risks

| Risk | Mitigation |
| :--- | :--- |
| BM25 tokenization diverges from TF-IDF | Reuse `vectorizer.build_analyzer()` — single token stream. |
| Grounding threshold miscalibrated | Constants in config; one calibration pass; `.env` override for the demo machine. |
| Chat-page surgery breaks the working demo | Inspector is one collapsible block under the sources block; playground lives in a separate file (`rag.html`) — chat page changes stay minimal. |
| `rank_bm25` dep objection | Inline 40-line BM25 fallback is pre-decided; swap is one class. |

## Explicitly out of scope this round

Chunking changes · reranker / embeddings / any model downloads · CI wiring ·
eval-set changes · CAD/solver/demo-catalog changes · repeated test loops.
