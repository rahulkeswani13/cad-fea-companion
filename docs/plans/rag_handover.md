# RAG implementation handover

Read `docs/adr/ADR-018-evidence-aware-rag.md`,
`docs/adr/ADR-019-local-neural-retrieval-selection.md`, and
`docs/plans/rag_evidence_plan.md` first. This file records the live status as of
2026-09-17.

| Stage | Branch or PR | Status |
|---|---|---|
| Corpus/index | [PR #5](https://github.com/rahulkeswani13/cad-fea-companion/pull/5) | Merged to `main`. |
| Original benchmark | [PR #6](https://github.com/rahulkeswani13/cad-fea-companion/pull/6) | Merged to `main`. |
| Benchmark repair | `codex/rag-benchmark-repair` | Complete locally; repaired fixture accepted by the user. |
| Retrieval | `codex/rag-neural-retrieval` | Active; existing implementation rebased for improvement and fresh development comparison. |
| Answer evidence | `codex/rag-evidence-answers` | Preserved prototype at `7810e50`; improve after retrieval freezes. |
| RAG Lab/acceptance | `codex/rag-demo-acceptance` | Preserved prototype at `c2fbf87`; improve after answer evidence. |

Recovery branches preserve the original local prototypes:
`codex/archive-rag-neural-v1`, `codex/archive-rag-answers-v1`, and
`codex/archive-rag-acceptance-v1`. They are snapshots, not branches to merge.

## Approved repaired baseline

The user accepted all 20 selected development cases on 2026-09-17. The fixture
records the matching content hash. Its fixed lexical development baseline is:

| Metric | Final four | Candidate pool (top 20) |
|---|---:|---:|
| Required-evidence recall | 0.8333 | 0.9470 |
| Answerable evidence recall | 0.8226 | 0.9435 |
| Critical evidence recall | 0.7273 | 0.9091 |
| Precision | 0.2500 | diagnostic only |
| nDCG | 0.6825 | diagnostic only |

The top-20/final-four gap makes ranking a major target. Five audited development
cases also miss required evidence in the lexical top 20 and need candidate
coverage, deterministic query rewriting, or evidence-led corpus improvements.

## Retrieval-stage rules

- Improve the existing local implementation; preserve public lexical behavior
  and expose neural availability/fallback honestly.
- Use local/free pinned models only.
- Select and tune only on development cases.
- Keep the original held-out split historical. Never rerun it or use it for a
  new claim.
- Freeze the retriever before an independent reviewer creates a fresh 30-case
  hidden set. Manually review every final answer on that set.
- Experimental bar: +5 percentage points answerable recall@4 over the repaired
  lexical baseline, higher nDCG, no critical-recall regression, and median
  retrieval below 500 ms.
- Final bar: 100% critical recall@4, >=90% answerable recall@4, >=90% correct
  answer/clarify/refuse behavior, >=95% supported factual claims, zero
  unsupported critical numerical claims, and median retrieval below 500 ms.

## ADR handling

ADR-018 records the benchmark repair and evaluation policy. Amend unpublished
ADR-019 with the new retrieval findings; amend ADR-020 and ADR-021 when their
stages are improved. Do not create ADR-022 unless a genuinely new architecture
is proposed and the user approves it.
