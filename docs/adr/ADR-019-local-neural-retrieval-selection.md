# ADR-019: Select local cross-encoder retrieval

**Status:** Accepted from the ADR-018 development benchmark, 2026-09-06.

## Context

ADR-018 approved a fixed comparison on the reviewed evidence benchmark: lexical
TF-IDF + BM25 + RRF; lexical plus local MiniLM embeddings; and the same candidate
union reranked by a local MiniLM cross-encoder. Candidate depth remained ten per
retriever, RRF damping remained 60, and final retrieval remained four passages.
Selection priority was critical-case evidence recall, answerable evidence recall,
ranking quality, then simplicity. No held-out result could influence selection.

## Decision

Select the `reranked` profile for subsequent answer experiments. It uses:

- `sentence-transformers/all-MiniLM-L6-v2` at revision
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`;
- `cross-encoder/ms-marco-MiniLM-L6-v2` at revision
  `233902d25c440f23af6f7d6e94d2946bac0bee0a`.

Development results were 0.7727 critical evidence recall@4, 0.8011 answerable
evidence recall@4, and 0.7291 nDCG@4. Embedding fusion tied the first two metrics
but reached 0.6760 nDCG@4; lexical reached 0.6364, 0.7177, and 0.6317.

After selection, the reranked profile was run once on held-out cases. It reached
0.6071 critical evidence recall@4, 0.7967 answerable evidence recall@4, 0.2667
precision@4, and 0.6387 nDCG@4. This misses the plan's 0.90 held-out recall
target. The result is retained as a failure signal; it is not used to retune,
relabel, or lower the target.

## Consequences

The existing lexical interface remains compatible. The additive profile API
reports requested and active profiles, exact model revisions, timing,
availability, and fallback reason. Interactive profile requests fall back
visibly to lexical retrieval if local models cannot load. Strict experiments
instead report the neural profile as unavailable and return no substituted
scores.

The cross-encoder adds substantial latency: the recorded development median was
338.78 ms/query versus 7.56 ms for embedding fusion and 0.62 ms for lexical.
Answer-quality work may use the selected profile, but final acceptance remains
blocked by held-out retrieval quality and later answer/citation evaluation.
