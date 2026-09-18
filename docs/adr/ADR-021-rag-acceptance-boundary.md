# ADR-021: Separate development inspection from independent RAG acceptance

**Status:** Accepted integration decision. Overall RAG is **Not accepted**.

## Context

The RAG Lab needs to explain why a retriever was selected and whether the whole
system is acceptable. Those are different questions. Development cases may be
inspected and tuned, while the independently authored hidden-v2 cases must not
become a second development set. Showing hidden queries, labels, or per-case
misses in the product would invite tuning against the only remaining independent
evidence. A development success must also never visually override an
independent failure or pending answer review.

## Decision

The comparison surface presents development and independent results in separate
rows and labels their roles. It may expose development case queries, approved
evidence groups, found and missing evidence, active/fallback retrieval profile,
and the top retrieved passages. It must not serve hidden-v2 queries, labels,
expected evidence, or per-case results. The hidden surface is aggregate only.

`eval/build_rag_acceptance_report.py` is the single deterministic aggregation
rule. It reads the frozen development comparison and immutable hidden-v2
retrieval report, optionally adds answer-evaluation and completed manual-review
summaries, and emits no hidden per-query data. Missing inputs are pending or
failed, never passes. Overall acceptance requires all ADR-018 targets:

- independent answerable evidence recall@4 at least 0.90;
- independent critical evidence recall@4 exactly 1.00;
- median retrieval below 500 ms;
- all 30 hidden answers generated and manually reviewed;
- answer/clarify/refuse behavior accuracy at least 0.90;
- supported factual-claim rate at least 0.95; and
- zero unsupported critical numerical claims.

The advisory semantic judge is reported separately from mandatory manual
review. Answer-quality acceptance is calculated from 30 per-case human marks
bound to the exact answer-report hash; an advisory judge score, typed aggregate
percentage, or bare "review complete" flag cannot satisfy those gates. A
delegated AI review may document a failure, but only a review explicitly marked
`reviewer_type: human` can provide independent sign-off. The API serves the
committed aggregate acceptance report and a distinct
development-only catalog/inspector. `comparison-report` remains an additive
alias for compatibility. Both chat consoles display the legacy grounding value
as a **retrieval match** and the bounded claim result as **answer evidence**;
neither label means engineering verification. Canonical evidence spans and
legacy quote provenance appear only under Technical details so the main answer
remains readable.

## Consequences

The RAG Lab can explain the selected design without leaking independent cases.
Its current top-level state is **Not accepted**: development reranking passes,
but hidden-v2 reranked recall is 0.80 answerable and 0.775 critical, below the
final targets. All 30 answers were generated; the delegated review measured
40% correct behavior, 43.9% supported factual claims, and zero critical numeric
violations, below the 90% and 95% answer targets. The advisory judge likewise
measured 40% semantic accuracy and 47.22% supported factual claims. Independent
human sign-off was not performed, but retrieval and answer-quality failures
already make acceptance impossible.
Improving retrieval from these hidden misses is prohibited; a future retrieval
change needs a new freeze and a new independently authored hidden evaluation.
Because this integration publishes the hidden fixture, generated answers,
diagnostics, review packets, and delegated review, every one of those artifacts
is retired and unusable as independent evidence for future RAG evaluation.

The committed aggregate report is reproducible from the frozen development and
hidden retrieval reports plus the frozen answer and delegated-review artifacts.
A UI or API change cannot convert pending or failing evidence into acceptance,
because tests compare the committed artifact to the deterministic builder and
verify that hidden per-case material is absent.

The later ADR-020 span amendment is a compatibility-preserving structural fix.
It does not rewrite the completed hidden-v2 answer report, rerun Gemini, or alter
this **Not accepted** result.

The user approved integrating the completed experimental series into `main`
through additive review gates and marking the verified stopping point with the
annotated tag `rag-evidence-release`. The tag records closure of this experiment;
it is not a production release, an acceptance claim, or a change to packaging.
