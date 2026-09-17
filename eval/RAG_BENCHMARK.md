# Evidence benchmark (ADR-018, benchmark-repair stage)

This is a **repaired fixture awaiting user review**, not a claim that generated
answers pass. It contains 100 cases: 70 development and 30 historical held-out,
including 20 critical cases. Twenty selected development examples are rendered
in `reviews/rag_benchmark_review.md` for review before tuning. The repair audit
is recorded in `reviews/rag_benchmark_audit.md`.

## Run the fixed baseline

From the repository root:

```sh
GEMINI_API_KEY= EVAL_JUDGE=0 .venv/bin/python eval/run_rag_benchmark.py \
  --output eval/reports/rag_lexical_baseline.json \
  --review-output eval/reviews/rag_benchmark_review.md
```

This is the existing lexical pipeline: no model downloads, generated answers,
API calls, or parameter tuning. Follow-up cases use the latest message alone;
future conversation-aware retrieval must be compared explicitly rather than
silently supplying a gold rewritten question.

The normal `eval/run_eval.py` includes fixture integrity/review-guard cases and
compact development evidence metrics. Existing document hit@4/MRR remain for
continuity. The standalone report includes development failure details.

## What the labels mean

Each required evidence group describes one needed piece of evidence. Equivalent
passages can appear as alternatives. A retrieved hit earns credit only when
its source, section identity and annotated quote match. Quotes are checked
against both raw documents and actual chunks, so the fixture cannot silently
accept a wrong section from the right document.

- **Evidence recall@4:** fraction of required evidence groups found, averaged
  across cases with required evidence. Also report answerable-case recall
  separately from cases retrieving an explicit limitation.
- **Precision@4:** relevant unique passages divided by four; empty slots earn
  no credit. Repeating a returned passage cannot inflate precision.
- **nDCG@4:** binary passage relevance discounted by rank, normalized against
  all gold-relevant chunks in the corpus. It does not substitute for group
  recall: repeated caveats can make multiple passages relevant to one group.
- Cases with no required evidence remain in the report with null retrieval
  scores. They are not free successes and are not removed from the benchmark.
- Expected actions, support status, facts, forbidden claims and numeric
  expectations are labels for subsequent answer evaluation. PR 2 does not
  execute or grade those answers. `injected_context`, when present, is an
  adversarial answer-eval fixture only, never ingested or used as real evidence.

Every report includes corpus and benchmark hashes, split, review status,
configuration and the explicit `answer_evaluation: not_run` marker.

The standalone report also measures the lexical top-20 candidate pool. This
separates evidence that was found but ranked below the final four from evidence
that lexical candidate retrieval missed entirely. `unjudged_same_source` lists
wrong or unlabelled passages from a labelled document for review; it never adds
metric credit.

## Review and held-out discipline

Review the 20 examples for useful expected behavior, source support, engineering
applicability and prohibited conclusions. Reply with case IDs/corrections or
accept all 20. The review is a sample, not independent validation of all 100.

After explicit user acceptance, record `review.status = approved` and
`review.benchmark_hash = benchmark_hash(benchmark)` in the fixture. This change
is made only in response to the user's review. Label, corpus, or review-selection
changes invalidate the approval hash. Never mark approval automatically after
validation or tests pass.

Tuning entrypoints must call `require_review`. While pending,
`--split heldout` exits nonzero. The original held-out cases were already run by
superseded local experiments and are now historical: do not rerun them, tune to
them, or use them for a new quality claim. Once retrieval is frozen, an
independent reviewer creates a fresh 30-case hidden set. All 30 generated answers
receive manual review.

The initial lexical development baseline is permitted before review because its
configuration is fixed, and is explicitly provisional. Do not tune retrieval,
rewrite labels to reward a result, lower acceptance targets, or drop difficult
questions while reviewing baseline misses.

## Quality bars belong to later stages

An experimental retriever must improve answerable recall@4 by at least five
percentage points over this repaired lexical baseline on the fresh hidden set,
increase nDCG, avoid a critical-recall regression, and keep median retrieval
below 500 ms.

Final acceptance requires 100% critical recall@4, >=90% answerable recall@4,
>=90% correct answer/clarify/refuse behavior, >=95% supported factual claims,
zero unsupported critical numerical claims, and median retrieval below 500 ms.
Report actual counts and limitations. Missing reviews are pending, not passing.
