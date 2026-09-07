# RAG implementation handover

Read `docs/adr/ADR-018-evidence-aware-rag.md` and
`docs/plans/rag_evidence_plan.md` first. This file records the live status.

| PR | Branch | Status |
|---|---|---|
| [#5](https://github.com/rahulkeswani13/cad-fea-companion/pull/5) | `codex/rag-corpus-indexing` | Open; CI passed. Curated corpus, ADR exclusion, chunks, safe index rebuild. |
| [#6](https://github.com/rahulkeswani13/cad-fea-companion/pull/6) | `codex/rag-benchmark` | Open; based on #5. Passage-level benchmark and review gate. |
| 3 | Not started | Blocked on benchmark review. Embeddings and reranker comparison. |
| 4 | Not started | Follow-ups and answer-evidence assessment. |
| 5 | Not started | RAG Lab comparison UI and final report. |

PR 1 commits: `7137e45`, `7e34d24`. PR 2 commit: `3ce61b1`.

## Required checkpoint

The user must review the 20 selected development cases in
`eval/reviews/rag_benchmark_review.md`. Ask for either `accept all 20` or
case IDs with corrections. Do not start retrieval tuning or held-out retrieval
before that response.

On explicit acceptance, and only then, set `review.status` to `approved` and
`review.benchmark_hash` to the current `benchmark_hash(benchmark)` in
`eval/rag_benchmark.json`. Changes to labels, corpus, or selected review cases
invalidate approval by design.

## Verified PR 2 state

- Full pytest: **360 passed**, 3 existing deprecation warnings.
- Key-free eval: **74 passed**, 5 judge-only cases skipped, no failures.
- FreeCAD smoke: cantilever and brake-pedal completed without fallback warnings.
- Lexical development baseline:
  `eval/reports/rag_lexical_baseline.json`.

| Metric | Value |
|---|---:|
| Required-evidence recall@4 | 0.7576 |
| Answerable evidence recall@4 | 0.7667 |
| Precision@4 | 0.2235 |
| nDCG@4 | 0.6453 |

These are provisional retrieval-only measurements, not answer-quality results.
No paid API calls, model downloads, retrieval tuning, or generated-answer
grading occurred.

## Important mechanics

- The fixture has 100 cases: 70 development, 30 held-out, 20 critical.
- Passage credit requires the source, section ID, and quote; a right-document
  wrong-section result gets no credit.
- No-evidence cases keep null retrieval metrics and never become passing answers.
- `eval/run_rag_benchmark.py --split heldout` exits before retrieval while
  review is pending; do not bypass it.
- `eval/rag_labels.json` hit@4/MRR remains document-level continuity data, not
  answer correctness.

## PR 3 after approval

Create a branch from `codex/rag-benchmark`. Compare the same corpus, chunks,
benchmark, and final k across: lexical TF-IDF + BM25 + RRF; lexical plus local
`sentence-transformers/all-MiniLM-L6-v2`; and that candidate union reranked by
local `cross-encoder/ms-marco-MiniLM-L6-v2`.

Pin model revisions, report availability and timing, preserve visible lexical
fallback if models fail, tune only on development cases, and run held-out once
after choosing by critical cases, evidence recall, ranking, then simplicity.
Local downloads are allowed; paid APIs and billing changes are not.
