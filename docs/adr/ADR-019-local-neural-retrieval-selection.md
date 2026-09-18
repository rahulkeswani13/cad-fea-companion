# ADR-019: Select local cross-encoder retrieval

**Status:** Accepted from the ADR-018 development benchmark, 2026-09-06;
amended after benchmark repair and independent retrieval evaluation,
2026-09-17.

## Context

ADR-018 approved a fixed comparison on the reviewed evidence benchmark: lexical
TF-IDF + BM25 + RRF; lexical plus local MiniLM embeddings; and the same candidate
union reranked by a local MiniLM cross-encoder. Candidate depth remained ten per
retriever, RRF damping remained 60, and final retrieval remained four passages.
Selection is gated by the amended ADR-018 experimental bar before critical-case
evidence recall, answerable evidence recall, ranking quality, and simplicity
break ties. The original held-out set is retired and cannot influence selection.

## Decision

Select the `reranked` profile for subsequent answer experiments. It uses:

- `sentence-transformers/all-MiniLM-L6-v2` at revision
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`;
- `cross-encoder/ms-marco-MiniLM-L6-v2` at revision
  `233902d25c440f23af6f7d6e94d2946bac0bee0a`.

Neural profiles apply inspectable deterministic query expansion for nine narrow
engineering question forms exposed by the development failure audit: design
regions, pedal geometry/selection, design-program transactions, PA12 environment
limits, cantilever dimensions/orientation, beam-theory evidence, and verification
scope. Rules depend on query text only, preserve the original text, and are
reported in retrieval metadata. Lexical fallback remains unchanged.
Expansion supplies vocabulary, never numeric answers or benchmark identifiers.

On the repaired development benchmark, lexical reached 0.7273 critical
recall@4, 0.8226 answerable recall@4, and 0.6825 nDCG@4. Embedding fusion reached
0.8636, 0.9274, and 0.7697 at 6.55 ms median/query. Reranking reached 1.0000,
0.9919, and 0.8728 at 318.99 ms median/query. Both neural profiles clear the
development-side experimental gate; reranking wins on critical recall, then
answerable recall and ranking quality.

The original held-out result is historical and has been removed from the active
comparison report. The CLI rejects attempts to rerun that split. These results
freeze the retriever for independent evaluation; they are not a generalization
or final-acceptance claim. A separate reviewer must author a fresh 30-case hidden
set after this freeze. The report records a SHA-256 fingerprint over chunking,
lexical-store, and neural-retrieval source; hidden evaluation must reject drift.

The independent reviewer subsequently authored 30 fresh cases without inspecting
the development labels, comparison results, or neural implementation. The
fixture binds corpus fingerprint `34517bc613faa567` and retriever fingerprint
`3ea360594b2f62ac5e63bc3d219cbebb7207e29bfd9d6f7b744f74feb4617326`.
The frozen retriever was then evaluated once:

| Profile | Critical recall@4 | Answerable recall@4 | nDCG@4 | Median/query |
|---|---:|---:|---:|---:|
| Lexical | 0.6750 | 0.6500 | 0.5650 | 0.65 ms |
| Frozen reranked | 0.7750 | 0.8000 | 0.6816 | 348.92 ms |

Reranking passes the experimental gate: answerable recall improves by 15
percentage points, nDCG improves, critical recall does not regress, and median
latency remains below 500 ms. It does **not** meet the accepted-RAG retrieval
bar of 100% critical recall and at least 90% answerable recall. The hidden result
is evidence, not a new tuning set; retrieval code and corpus must not be changed
in reaction to its per-case misses and the evaluation must not be rerun.

## Consequences

The existing lexical interface remains compatible. The additive profile API
reports requested and active profiles, exact model revisions, timing,
availability, and fallback reason. Interactive profile requests fall back
visibly to lexical retrieval if local models cannot load. Strict experiments
instead report the neural profile as unavailable and return no substituted
scores.

The cross-encoder adds substantial latency but remains below the 500 ms median
gate on this machine. Query expansion is deliberately narrow and must not grow
by reacting to the fresh hidden-set failures. Answer-quality work may use the
selected profile as an experimental input, with missing evidence producing a
partial answer or refusal. The retrieval stage is not final-acceptance evidence;
meeting the stricter ADR-018 bar after any future retrieval change requires a
new freeze and a newly independent hidden evaluation.
