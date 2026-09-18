# ADR-020: Bound generated answers to identified evidence

**Status:** Accepted for PR 4, 2026-09-06; amended for the independent hidden-v2
workflow and deterministic evidence spans, 2026-09-17. Final answer acceptance
failed.

## Context

Retrieval rank and the legacy grounding label do not establish that an answer is
supported. Follow-up questions need limited conversational and current-CAD
context without turning the full transcript into an uncontrolled query. A model
can also cite a real passage that does not entail its claim, so source identity,
exact provenance, semantic support, and engineering verification must remain
separate concepts.

The frozen retriever already ran once on the independently authored hidden-v2
set. Answer evaluation must consume that immutable retrieval report rather than
rerun retrieval or silently turn hidden misses into tuning data.

## Decision

The chat retrieval query contains the current question, at most one prior user
question when the wording is elliptical, and a compact current-CAD descriptor.
Chat requests the ADR-019 reranked profile and exposes its active profile,
fallback reason, rewrite metadata, and timing.

Every final model response is requested as a structured draft containing an
action, complete factual claims, evidence-span IDs, and explicit gaps. Parent
evidence IDs distinguish the current question (`Q1`), current
CAD state (`C1`), four retrieved passages (`D1`–`D4`), and at most six current
turn tool results (`T1`–`T6`). Document authority, applicability, and scope
conditions remain attached. Retrieval order is never an authority rule, and
`Q1` cannot establish the truth of the user's premise.

A deterministic answer-time segmenter gives prose sentences, header-aware table
rows, and individual CAD/tool JSON fields readable IDs such as `D1:S3`. The
checker resolves each cited span to canonical source text; the model does not
copy it. It rejects unknown or missing spans, failed tool results used as factual
support, and numeric values absent from the cited spans. Legacy responses remain
compatible through exact-quote matching followed by conservative Unicode,
whitespace, punctuation, and Markdown/table normalization; paraphrasing does not
pass that fallback.

At most one repair attempt may correct rejected claims. Claims that already
passed are retained, only failed claims are sent for repair, and a failed repair
returns the supported portion with explicit gaps. Only claims that pass those
structural checks are rendered. The
public states remain `supported`, `partially_supported`, `insufficient`, and
`check_unavailable` for compatibility, but the envelope separately reports
`semantic_check: pending_manual_or_judge`. A structurally supported claim must
never be presented as semantically verified or as engineering validation.

The answer evaluator reads the saved hidden-v2 ranked chunk IDs whose report
SHA-256 is
`316e3c9c7a12846d187e754f4d93eaada3ce58b995a9336818a4335dbe5d78cb`.
It rejects report, corpus, or retriever drift and never calls retrieval. Model
generation and the advisory semantic judge require explicit confirmation that
the configured Gemini model/project is free-eligible, are cached by complete
inputs and versions, and are limited to ten uncached cases per process. All 30
final answers require manual review; pending generation, judge errors, quota
exhaustion, and missing human review are never passes.

## Consequences

The existing answer string and lexical behavior remain available. Additive chat
and stream fields expose retrieval selection, bounded query context, claim-level
span IDs, canonical source text, provenance method, legacy quotes, gaps, repair
status, and whether semantic review has occurred. A malformed legacy/plain
response preserves its text for compatibility
but is labeled `check_unavailable` and must not be called verified.

Exact quote validation materially strengthens provenance but cannot determine
entailment, resolve every contradiction, or validate an engineering result.
Those questions remain with the separate semantic judge and the mandatory human
review. Since hidden-v2 retrieval missed the final retrieval bar, absent evidence
must yield a partial answer, clarification, or refusal; answer generation cannot
repair missing retrieval evidence by inventing facts.

The completed hidden-v2 answer run generated all 30 answers. Seven were labeled
supported, 23 insufficient, 19 needed a repair attempt, and six had a structured
action mismatch. The advisory judge scored 12/30 semantically correct (40%),
47.22% supported factual claims, and zero critical numeric violations. It also
reported 35 quote-related gaps, showing that exact-substring validation is too
brittle to serve as the sole evidence contract.

The span amendment addresses that structural brittleness without changing the
corpus, chunker, retriever, frozen reports, semantic-review boundary, or
acceptance result. It adds no new hidden-set accuracy claim. A fresh independent
evaluation is deferred until a future retrieval revision is frozen.

At the user's request, Codex completed a delegated review of all 30 answers. It
scored 40% correct user-facing behavior, 43.9% supported factual claims, and zero
critical numeric violations. This is recorded as `delegated_ai_complete`, not
independent human approval, and cannot make the system accepted. Hidden-v2 is
diagnostic evidence only; improving the design requires a new freeze and a new
independent evaluation rather than tuning against these cases.
