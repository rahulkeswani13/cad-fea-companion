# Evidence benchmark (ADR-018, PR 2)

This is a **draft fixture awaiting user review**, not a claim that generated
answers pass. It contains 100 cases: 70 development and 30 held-out, including
20 critical cases. Twenty selected development examples are rendered in
`reviews/rag_benchmark_review.md` for review before tuning.

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

## Review and held-out discipline

Review the 20 examples for useful expected behavior, source support, engineering
applicability and prohibited conclusions. Reply with case IDs/corrections or
accept all 20. The review is a sample, not independent validation of all 100.

After explicit user acceptance, record `review.status = approved` and
`review.benchmark_hash = benchmark_hash(benchmark)` in the fixture. This change
is made only in response to the user's review. Label, corpus, or review-selection
changes invalidate the approval hash. Never mark approval automatically after
validation or tests pass.

Tuning entrypoints must call `require_review`. The held-out runner also calls
it before retrieving any query. While pending, `--split heldout` exits nonzero.
After review, held-out evaluation must follow development selection; do not use
held-out results to select a winner. Any cases used to repair a held-out failure
become development evidence; fresh held-out cases are required for a new claim.

The initial lexical development baseline is permitted before review because its
configuration is fixed, and is explicitly provisional. Do not tune retrieval,
rewrite labels to reward a result, lower acceptance targets, or drop difficult
questions while reviewing baseline misses.

## Final acceptance belongs to later PRs

All critical checks and answer reviews must pass; targets are >=90% answerable
required-evidence recall, >=90% correct answer/clarify/abstain behavior, and >=95%
supported factual claims in reviewed held-out answers, with no unsupported
critical numeric claim. Report actual counts and limitations. Free-quota skips
are pending, not passing. See the approved plan for the complete delivery scope.
