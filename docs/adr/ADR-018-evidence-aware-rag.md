# ADR-018: Curated evidence and evaluated RAG

**Status:** Accepted — user-approved implementation plan, 2026-09-06.

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

## Delivery

Five sequential PRs: (1) corpus/index, (2) benchmark and review checkpoint,
(3) retrieval experiments, (4) evidence-aware answers and follow-ups,
(5) comparison demo and final evaluation. Estimated total engineering effort
50–70 hours, excluding user-review and free-quota waits. Every PR ships its
own tests, eval coverage and demo notes. This ADR is amended for findings;
it does not imply that future phases are already implemented.

## Alternatives and consequences

Keeping ADRs in retrieval preserves historical explanations but mixes outdated
decisions with current behavior. Broad directory ingestion makes new material
implicitly authoritative. A manifest requires deliberate maintenance instead.
Lexical retrieval remains the no-model fallback; added complexity must earn its
place on quality, with simplicity breaking ties. Any eventual answer-support
label is an assessed evidence claim, never a certification of part safety.
