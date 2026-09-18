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
| Retrieval | `codex/rag-neural-retrieval` | Frozen and independently evaluated locally; experimental gate passed, final retrieval bar missed. |
| Answer evidence | current worktree; prototype archived at `7810e50` | Complete and evaluated locally; answer-quality targets failed. |
| RAG Lab/acceptance | current worktree; prototype archived at `c2fbf87` | Complete locally; aggregate status is **Not accepted**. |

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

## Frozen development result

The repaired comparison selects `reranked`. The original held-out set was not
run and the CLI now rejects it.

| Profile | Critical recall@4 | Answerable recall@4 | nDCG@4 | Median/query |
|---|---:|---:|---:|---:|
| Lexical | 0.7273 | 0.8226 | 0.6825 | 0.66 ms |
| + embeddings and rewrites | 0.8636 | 0.9274 | 0.7697 | 6.55 ms |
| + cross-encoder and rewrites | 1.0000 | 0.9919 | 0.8728 | 318.99 ms |

Both neural profiles satisfy the development-side experimental gate. Reranking
wins the documented selection order and was frozen before the fresh,
independently authored 30-case hidden set was created. Do not add rewrite rules
or tune the retriever after seeing that set. The comparison report's
`retriever_fingerprint` makes this freeze enforceable without relying on an
unpublished Git commit.

## Independent hidden-v2 result

An independent reviewer authored `eval/rag_hidden_v2.json` after the freeze:
30 fresh cases (20 answer, 3 clarify, 7 refuse; 20 critical). Every exact
evidence quote resolves against the frozen 98-chunk corpus. The one-time runner
rejects corpus/retriever fingerprint drift and refuses to overwrite its report.

| Profile | Critical recall@4 | Answerable recall@4 | nDCG@4 | Median/query |
|---|---:|---:|---:|---:|
| Lexical | 0.6750 | 0.6500 | 0.5650 | 0.65 ms |
| Frozen reranked | 0.7750 | 0.8000 | 0.6816 | 348.92 ms |

The reranker passed all four experimental checks, including a +0.15 answerable
recall gain. It missed the final retrieval requirements of 1.00 critical recall
and at least 0.90 answerable recall. Treat
`eval/reports/rag_hidden_v2_retrieval.json` as immutable evidence: do not rerun
it or tune retrieval from its misses. PR 4 may proceed with the frozen retriever
only as an experimental input, making weak or absent evidence produce a partial
answer or refusal. Any future retrieval change needs a new freeze and a new
independent hidden evaluation before it can make a final-acceptance claim.

## Answer-evidence stage

The preserved PR 4 prototype has been integrated into the current implementation
and strengthened. Chat now requests the frozen reranked profile, resolves only a
bounded follow-up context, names `Q1`, `C1`, `D1`–`D4`, and `T1`–`T6` evidence,
and exposes retrieval and answer-evidence metadata additively. The bounded check
validates evidence IDs, successful tool results, exact numeric provenance, and
deterministic canonical spans. Prose sentences, header-aware table rows, and
CAD/tool fields receive readable IDs such as `D1:S3`. Legacy copied quotes remain
compatible through conservative formatting normalization. Semantic entailment
remains pending, and the one repair attempt preserves already-supported claims.

`eval/run_rag_answer_evaluation.py` consumes the existing one-time hidden-v2
ranked chunks; it does not rerun retrieval. It rejects report/corpus/retriever
drift, caches complete inputs, permits at most ten uncached model calls per run,
and requires explicit free-eligibility confirmation. Generation and advisory
semantic judging completed for all 30 cases. The answer report is
`eval/reports/rag_hidden_v2_answers.json`, bound to SHA-256
`31e99cba9210756dc3bab5817abda52f1778dc981ed3c0fd485eaf99150c2698`.
The advisory judge measured 40% semantic accuracy, 47.22% supported factual
claims, and zero critical numeric violations. Seven answers were structurally
supported, 23 insufficient, 19 needed a repair attempt, and the report contains
35 quote-related gaps.

At the user's request, Codex reviewed all 30 answers in
`eval/reviews/rag_hidden_v2_ai_review.json`. That delegated review measured 40%
correct user-facing behavior, 43.9% supported factual claims, and zero critical
numeric violations. It is explicitly `reviewer_type: delegated_ai`, not an
independent human sign-off. PR 4 and the overall RAG series are not accepted.

The post-evaluation span amendment fixes a demonstrated structural failure mode
but does not modify or rerun the immutable answer report. Its claim is limited to
the tested evidence contract; it makes no new hidden-set accuracy claim.

## RAG Lab and acceptance stage

`eval/build_rag_acceptance_report.py` combines the frozen development and
hidden-v2 reports without copying hidden per-case rows. The committed
`eval/reports/rag_acceptance_summary.json` is reproducible from those inputs and
currently reports `accepted: false`: independent retrieval and answer quality
both fail. The delegated review is complete but cannot satisfy the human
sign-off condition.

The RAG Lab shows development and independent aggregate metrics separately. Its
case picker is development-only and may show approved found/missing evidence and
top passages. The API never serves hidden queries, labels, or per-case results.
Both the React and classic chat consoles present retrieval match and answer
evidence as separate labels with profile fallback, gaps, and pending semantic
review under technical details. ADR-021 records this boundary.

The provider-backed run is complete and should not be rerun for this evaluation.
The cached outputs and report are the evidence. Even a passing answer review
could not override the already failed frozen independent retrieval bar.

After the final answer/judge report is stable, create the review worksheet with
`eval/create_rag_manual_review.py --answer <answer-report> --output <review-json>`.
The worksheet is bound to the exact report hash and requires all checklist marks
for every case. `eval/build_rag_acceptance_report.py --answer <answer-report>
--manual-review <review-json>` derives the review metrics from those rows; it
does not trust typed aggregate scores or a completion flag. Only
`reviewer_type: human` can satisfy independent sign-off; the completed delegated
AI review can document failure but cannot accept the system.
