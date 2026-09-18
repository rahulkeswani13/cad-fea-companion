# ADR-018: Curated evidence and evaluated RAG

**Status:** Accepted — user-approved implementation plan, 2026-09-06;
benchmark-repair amendment accepted 2026-09-17.

The engineering assistant needs current, applicable reference knowledge, not the
history of implementation decisions. ADRs remain in the repository, but are
excluded from the default corpus. This supersedes ADR-014's inclusion of ADRs;
its fail-closed principle remains. Current facts are maintained in reference
documents and checked against code and authoritative material data.

## Decisions

- An explicit document manifest selects the default corpus and records source,
  topic, authority, review/version information, and applicability. The approved
  `rag_corpus_dirs` default becomes `docs/reference`; explicit caller/environment
  corpus roots retain their legacy behavior for compatibility and experiments.
- Evidence has document/section identity and source locations. Section-aware
  chunks preserve table headers and repeat applicability caveats. Content,
  metadata and chunker configuration identify an index; failed rebuilds retain
  the accepted index. Persist candidates atomically and retain a rollback copy.
- Existing tool contracts and retrieval fields stay compatible. Additive index
  and evidence metadata are approved. `score` remains TF-IDF cosine; legacy
  `grounding` remains a retrieval diagnostic, not answer verification.
- Subsequent PRs compare lexical, lexical+local embeddings, and reranked
  retrieval on the same benchmark. Approved initial dependencies are local
  Sentence Transformers models all-MiniLM-L6-v2 and
  cross-encoder/ms-marco-MiniLM-L6-v2, pinned when provisioned. No paid APIs,
  hosted vector database, billing changes, or broad domain expansion.
- Answer evidence assessment is separate from retrieval ranking. Supported,
  partially supported, insufficient, and unavailable assessment states must
  preserve engineering applicability and solver verification limits. No
  user-facing confidence percentages. Additive chat/stream evidence fields,
  comparison API and manifest-restricted source viewer are approved in later PRs.
- Benchmark evidence labels never enter the corpus. User reviews 20 development
  examples before tuning; 70 development / 30 held-out cases measure retrieval,
  answer correctness, citation support and abstention separately. Critical
  unsupported claims block completion; skipped free-quota evals are not passes.
- The 2026-09-06 benchmark review corrected two evidence-backed negative answers
  from `abstain/insufficient` to `answer/supported`. It also replaced false
  supplier-specific PA12 provenance with explicitly provisional screening
  assumptions and states that repeating the current linear-static solve cannot
  verify large-deflection polymer behavior.

### 2026-09-17 benchmark-repair amendment

The first local neural experiment exposed benchmark defects as well as real
retrieval failures. The development-only audit therefore repairs five cases
with incomplete evidence alternatives, one wrong section identity, and one
corpus-coverage gap.
Those changes invalidate the earlier approval hash and lexical baseline. The
repaired fixture returns to `pending` until the user reviews every changed case,
every critical development case, and the selected continuity cases (20 total).
The user accepted all 20 on 2026-09-17; the fixture records the matching content
hash, and later label or corpus changes invalidate that approval.

Candidate-pool recall at 20 is reported alongside final recall at four so a
ranking miss can be distinguished from a candidate-retrieval miss. Hits from a
labelled source that match no approved passage are review leads only; they never
receive relevance credit automatically.

The original held-out set is historical because it was already exercised during
the local experiments. It must not be rerun, tuned against, or used for a fresh
generalization claim. After the retriever is frozen, an independent reviewer
creates a new 30-case hidden set and manually reviews all 30 final answers.

Two quality bars apply:

- **Experimental retriever:** on the fresh hidden set, answerable recall@4 must
  improve by at least five percentage points over the repaired lexical baseline,
  nDCG must increase, critical recall must not regress, and median retrieval must
  remain below 500 ms.
- **Accepted RAG:** 100% critical recall@4, at least 90% answerable recall@4, at
  least 90% correct answer/clarify/refuse behavior, at least 95% supported factual
  claims, zero unsupported critical numerical claims, and median retrieval below
  500 ms.

Retrieval improvements remain local and free. Deterministic query rewriting and
evidence-led corpus additions are allowed; weak evidence yields a partial answer
or refusal. Existing stage 3–5 implementations are reusable prototypes, not
accepted results, and are improved in place while public interfaces remain
additive. This amendment updates ADR-018; it does not create ADR-022. A genuinely
different architecture requires a separate decision before implementation.

## Delivery

Five sequential PRs: (1) corpus/index, (2) benchmark and review checkpoint,
(3) retrieval experiments, (4) evidence-aware answers and follow-ups,
(5) comparison demo and final evaluation. Estimated total engineering effort
50–70 hours, excluding user-review and free-quota waits. Every PR ships its
own tests, eval coverage and demo notes. This ADR is amended for findings;
it does not imply that future phases are already implemented.

The repaired retrieval stage selected local cross-encoder reranking on
development evidence quality. ADR-019 records pinned revisions, inspectable
deterministic query expansion, timing, and the retirement of the previously
observed held-out set. On a fresh independently authored 30-case set, the frozen
reranker passed the experimental gate but missed the accepted-RAG retrieval bar:
0.7750 critical recall@4 and 0.8000 answerable recall@4. ADR-019 records the full
result. The hidden set is not a tuning set and must not be rerun.

PR 4 adds bounded follow-up resolution and structured claim/evidence checks.
ADR-020 records the exact-quote provenance requirement, the one-repair limit,
reuse of the immutable hidden-v2 retrieval report, and the remaining mandatory
semantic and manual reviews. Passing the bounded check is not semantic or
engineering verification.

PR 5 adds a fail-closed aggregate acceptance report and a development-only
evidence inspector. ADR-021 records the split boundary: development cases are
inspectable, hidden-v2 is aggregate-only, and development success cannot mask
independent failure or failed answer review. The current aggregate state is
**not accepted**; this is a truthful result, not a completed quality claim.

The final hidden-v2 answer run generated all 30 answers. Its advisory judge
measured 40% semantic accuracy and 47.22% supported factual claims, with zero
critical numeric violations. A delegated Codex review measured 40% correct
user-facing behavior and 43.9% supported factual claims, also with zero critical
numeric violations. Because the review was not independent human sign-off and
both retrieval and answer targets failed, the five-stage effort closes as a
documented unsuccessful experiment, not as accepted RAG.

## Alternatives and consequences

Keeping ADRs in retrieval preserves historical explanations but mixes outdated
decisions with current behavior. Broad directory ingestion makes new material
implicitly authoritative. A manifest requires deliberate maintenance instead.
Lexical retrieval remains the no-model fallback; added complexity must earn its
place on quality, with simplicity breaking ties. Any eventual answer-support
label is an assessed evidence claim, never a certification of part safety.
