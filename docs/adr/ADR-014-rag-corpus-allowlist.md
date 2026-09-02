# ADR-014: Curated RAG corpus via allowlist ingestion

Date: 2026-09-02 · Status: accepted

## Context

`ingest_docs` globbed all of `docs/**` and subtracted a denylist
(`PLAN.md`, `PLAN_F26.md`, any `docs/plans/` dir). That policy **fails
open**: the default for any new markdown file anywhere under `docs/` was
"ingested", so a stray working note, scratch doc, or roadmap draft would
silently join the grounding corpus the agent quotes from — and the corpus
is part of the eval fixture, so nothing would record that the retrieval
metrics now mean something different.

The corpus split that actually matters is by audience, not by folder:

- **reference** (the 7 product docs) — user-facing *what/how*;
- **decisions** (`docs/adr/`) — agent-facing *why*. ADRs stay in the
  corpus deliberately: they are what lets the agent explain its own
  behavior ("why no engine mount?", "why does `bcc` alias to xtruss?")
  without inventing a rationale, and several RAG eval cases are only
  answerable from them;
- **intentions & process** (plans, roadmap, demo/pitch material,
  contributor guides) — never corpus. The agent must describe the product
  as it is, not the roadmap as wished; pitch language must not leak into
  answers.

## Decisions

1. **Allowlist ingestion.** `Settings.rag_corpus_dirs` declares the corpus
   (default `["docs/reference", "docs/adr"]`, comma-separated
   `RAG_CORPUS_DIRS` env override). Only files under declared dirs are
   ingested; everything else is excluded *by default* — getting in is a
   deliberate act. The denylist constants are deleted; they existed only
   to compensate for scanning too wide.
2. **Two declared roots, not one `corpus/` folder.** ADRs stay at the
   conventional `docs/adr/` path (MADR convention, cross-links, the
   AGENTS.md contract references it). The fail-closed property comes from
   the explicit include-list; the physical layout keeps serving humans.
   The machine adapts to the repo, not the reverse.
3. **Product docs live in `docs/reference/`.** The move makes the two
   corpus roots declarable without exceptions; a root-level exception file
   (e.g. materials.md left loose in `docs/`) would defeat the property.
4. **File selection is a pure function.** `collect_corpus_files` returns
   `(path, source)` pairs with no store or disk side effects, so the
   fail-closed property is unit-testable without poisoning the global
   store or the persisted index.
5. **The corpus is versioned inside the eval fixture.** Every eval run
   records a corpus fingerprint (sorted path + chunk-count digest) in the
   report and history; `corpus_drifted` flags any change so a corpus edit
   can never silently reset what hit@4 / MRR mean (extends the H5 delta
   discipline to the corpus).

## Consequences

- `eval/rag_labels.json` source strings re-pinned to `docs/reference/...`;
  retrieval metrics re-baselined on this change (MRR shifted 0.967 → 0.942
  from corpus-ordering tie-breaks, honestly annotated in the history).
- New content under `docs/` is *not* ingested until it is placed in a
  declared dir — the inverse of the old failure mode.
- ADR prose and PLAN docs written before this change keep their historical
  `docs/...` paths; ADRs are records, not living docs.
- Ingestion results report the *declared* dir form (portable) — eval
  reports are committed artifacts, so no machine-specific paths.
