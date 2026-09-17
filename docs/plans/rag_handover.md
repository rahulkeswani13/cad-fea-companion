# RAG implementation handover

Read `docs/adr/ADR-018-evidence-aware-rag.md` and
`docs/plans/rag_evidence_plan.md` first. This file records the live status as of
2026-09-17.

| Stage | Branch or PR | Status |
|---|---|---|
| Corpus/index | [PR #5](https://github.com/rahulkeswani13/cad-fea-companion/pull/5) | Merged to `main`. |
| Original benchmark | [PR #6](https://github.com/rahulkeswani13/cad-fea-companion/pull/6) | Merged to `main`. |
| Benchmark repair | `codex/rag-benchmark-repair` | Active; implementation and provisional baseline complete, awaiting 20-case user review. |
| Retrieval | `codex/rag-neural-retrieval` | Existing local implementation at `f784c76`; preserve and improve after benchmark approval. |
| Answer evidence | `codex/rag-evidence-answers` | Existing local implementation at `7810e50`; preserve and improve after retrieval. |
| RAG Lab/acceptance | `codex/rag-demo-acceptance` | Existing local implementation at `c2fbf87`; preserve and improve after answer evidence. |

Immutable recovery names preserve the three local prototypes:
`codex/archive-rag-neural-v1`, `codex/archive-rag-answers-v1`, and
`codex/archive-rag-acceptance-v1`. They are safety snapshots, not branches to
merge. The active stage branches may be rebased onto the repaired benchmark so
the existing code is improved instead of rewritten.

## Current checkpoint

The user must review the 20 selected development cases in
`eval/reviews/rag_benchmark_review.md`. The selection contains every changed
case, every critical development case, and two PA12 continuity cases. Ask for
either `accept all 20` or case IDs with corrections. Do not tune retrieval or
run the historical held-out split before that response.

On explicit acceptance, and only then, set `review.status` to `approved` and
`review.benchmark_hash` to the current `benchmark_hash(benchmark)` in
`eval/rag_benchmark.json`. Changes to labels, corpus, or selected review cases
invalidate approval by design.

## Repaired provisional baseline

The development audit and its case-by-case classifications are in
`eval/reviews/rag_benchmark_audit.md`. The fixed lexical configuration reports:

| Metric | Final four | Candidate pool (top 20) |
|---|---:|---:|
| Required-evidence recall | 0.8333 | 0.9470 |
| Answerable evidence recall | 0.8226 | 0.9435 |
| Critical evidence recall | 0.7273 | 0.9091 |
| Precision | 0.2500 | diagnostic only |
| nDCG | 0.6825 | diagnostic only |

These measurements are provisional and retrieval-only. The large gap between
top-20 and final-four recall identifies ranking as a major problem, while five
audited cases also contain evidence absent from the lexical top 20. Because the
repair changed labels and added maintained evidence, the values are a new
baseline, not a retriever-only improvement over PR #6.

## Important mechanics

- The fixture has 100 cases: 70 development and 30 historical held-out, with 20
  critical cases.
- Passage credit requires the source, section ID, and quote; a right-document,
  wrong-section result gets no credit.
- Same-source unmatched hits are review leads only and never gain automatic
  relevance credit.
- No-evidence cases keep null retrieval metrics and never become passing answers.
- `eval/run_rag_benchmark.py --split heldout` exits before retrieval while
  review is pending. The old held-out set stays retired even after approval.
- `eval/rag_labels.json` hit@4/MRR remains document-level continuity data, not
  answer correctness.

## Next stage after approval

Update the existing neural-retrieval implementation on top of the repaired
benchmark. Keep the lexical fallback visible, use local/free models only, and
add deterministic query rewriting or evidence-led corpus material where the
audited misses justify it. Tune only on development data.

Freeze the chosen retriever before an independent reviewer creates a fresh
30-case hidden set. The experimental bar is +5 percentage points answerable
recall@4 over the repaired lexical baseline, higher nDCG, no critical-recall
regression, and median retrieval below 500 ms. Final acceptance has the stricter
ADR-018 bar and includes manual review of all 30 hidden-set answers.

ADR-018 is amended for this repair. Update unpublished ADR-019, ADR-020, and
ADR-021 with their corresponding implementation findings. Do not create
ADR-022 unless the work requires a genuinely new architectural decision, and
ask the user before doing so.
