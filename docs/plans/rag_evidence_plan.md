# Evidence-aware RAG delivery plan

Accepted 2026-09-06 after the design interview. Decision: ADR-018.

Amended 2026-09-17 after the first local experiment exposed benchmark defects
and contaminated the original held-out set. ADR-018 records the decision; this
is not a new ADR.

## Scope and ownership

Codex implements five sequential, independently verified PRs. Optional delegated
work uses GPT-5.6 Luna with high reasoning. The user reviews 20 development
benchmark examples before retrieval tuning. Target: an interview-ready local
engineering assistant with a path to a small pilot; no paid API use, multi-user
hosting, broad engineering-domain expansion, or confidence percentages.

Quality takes precedence over speed; measured quality ties favor simplicity.
Keep ADRs in the repo, exclude them from the default corpus, and maintain current
engineering/product facts in curated reference docs. Current CAD state and run
results come from tools. Evidence support never implies engineering validation.

## Five PRs

1. **Corpus/index:** manifest, reference cleanup and extraction, structured chunks,
   source provenance, content fingerprints, validated atomic replacement,
   startup reuse and rollback. Preserve existing interfaces.
2. **Benchmark:** 100 cases, 70 development / 30 held-out, grouped by related
   question family. Each has evidence, expected facts, prohibited claims,
   numeric/unit expectations and answer/clarify/abstain behavior. Twenty
   representative development cases require user review before tuning. Twenty
   critical cases span both splits. No benchmark labels enter ingestion.
3. **Retrieval:** improve the existing local implementation rather than rewrite
   it: lexical baseline; lexical + local all-MiniLM-L6-v2 embeddings;
   combined retrieval + ms-marco-MiniLM-L6-v2 cross-encoder. Pin downloaded
   revisions. Ten candidates/retriever, RRF 60, final k=4 as initial settings.
   Select on development quality (critical cases, evidence recall, ranking),
   then freeze it before independent confirmation on a fresh hidden set. Missing
   models fall back visibly in chat;
   experiments mark unavailable rather than mislabel a fallback.
4. **Answers:** resolve follow-ups using current question, recent conversation
   and CAD state; clarify ambiguity. Structured draft claims and evidence IDs,
   bounded evidence check, at most one repair. Return supported portions and
   explicit gaps. States: supported, partially supported, insufficient, or
   check unavailable. No unchecked draft is presented as verified. Source
   authority and conditions govern conflicts, not retrieval rank.
5. **Demo/acceptance:** extend RAG Lab comparison, development-question picker,
   found/missing evidence, model/config/timing diagnostics, restricted evidence
   viewer; update both chat surfaces. Reproducible report, failure analysis,
   walkthrough, demo script and interview questions.

## Evaluation and acceptance

Measure evidence recall/precision@4 and nDCG@4, retain hit@4/MRR for continuity,
then separately measure answers, citation support and abstention. Evidence
labels reference source sections/passages, not merely matching documents.
Generated-answer judge receives retrieved evidence, actual tool outputs and
reference expectations. Judge findings are advisory; critical cases also require
answer review. Do not resample only failures to hide unfavorable outcomes.

The original held-out split is historical because the local prototypes already
exercised it. Never rerun or tune against it. After retrieval is frozen, an
independent reviewer creates a fresh 30-case hidden set and manually reviews all
30 final answers.

The experimental bar on that fresh set is at least +5 percentage points
answerable recall@4 over the repaired lexical baseline, higher nDCG, no
critical-recall regression, and median retrieval below 500 ms. Final acceptance
requires 100% critical recall@4, >=90% answerable recall@4, >=90% correct
answer/clarify/refuse behavior, >=95% supported factual claims, zero unsupported
critical numerical claims, and median retrieval below 500 ms. Report counts and
limitations. Do not lower targets after observing failures; cases used to fix a
hidden-set failure are no longer hidden.

Use deterministic query rewriting and evidence-led corpus additions where
needed. Weak evidence produces a partial answer or refusal. Preserve public
compatibility with additive fields. Amend ADR-018 for benchmark policy and the
unpublished ADR-019 through ADR-021 for their stages; create no new ADR unless a
genuinely new architecture is proposed and approved.

Verify free Gemini model/project eligibility before API evaluations. No billing
changes or paid fallback. Serial batches of at most ten cases, cached by complete
inputs/versions; stop on quota exhaustion and resume later. Missing evaluations
are pending, never passing. CI stays key-free; real neural-model verification
runs locally. Existing repo pytest/eval/available-FreeCAD gates apply per PR.

## Effort

Corpus/index 10–14 h; benchmark 8–10 h; retrieval 8–12 h; answer behavior
12–16 h; demo/final verification 12–18 h. Total 50–70 engineering hours,
approximately 2–3 working weeks at 25–30 productive hours/week. User-review and
free-quota waits are additional. These are effort estimates, not agent-runtime
promises. PR 1 changes corpus and chunking; its metric changes are not evidence
of retriever-only improvement.
