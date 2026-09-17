# RAG development benchmark repair audit

**Status:** all 20 selected cases accepted by the user on 2026-09-17. This audit
uses development cases only. The original held-out cases were not inspected or
rerun.

The first neural comparison exposed sixteen development cases with missing
evidence. Each miss was reviewed against the maintained reference text and the
retrieved passage identity. A same-document hit was never accepted by itself.

| Cases | Classification | Resolution |
|---|---|---|
| `mat-002`, `mat-006` | Incomplete evidence alternatives | The retrieved alloy-specific sections independently contain the required modulus, density, and yield values. Add those passages as approved alternatives to the existing summary-table rows. |
| `mat-008` | Wrong section label | The AM-allowables caveat belongs to the document's top-level section, not `summary`. Correct the section identity without changing the expected answer. |
| `mat-009` | Incomplete evidence alternatives | The tool reference independently states that the brake-pedal material defaults to Al 6061-T6. Add it as an alternative. |
| `mat-011` | Incomplete evidence alternatives | The retrieved mild-steel passage contains both the 250 MPa ballpark and the teaching-value caveat. Add the caveat in that section as an alternative. |
| `mat-019` | Incomplete evidence alternatives | The verification reference independently states the default dimensions, load, 120 MPa result, and reference-calculation limitation. Add it as an alternative. |
| `mat-014` | Corpus coverage gap | The old table header did not support the labelled requirement that there is no universal best material. Add explicit maintained guidance about competing objectives and required design context. |
| `flow-002`, `flow-011`, `flow-022`, `mat-007` | Final-ranking miss | All required passages appear in the lexical top-20 candidate pool but not consistently in the final four. Keep the labels unchanged and address ranking in retrieval work. |
| `flow-010`, `mat-016`, `mat-017`, `mat-022`, `mat-026` | Candidate-retrieval miss | At least one required passage is absent even from the lexical top-20 candidate pool. Keep the labels unchanged and address query coverage/chunk selection in retrieval work. |

## Repaired provisional baseline

The repair changes labels and adds one maintained material-selection passage,
so it deliberately invalidates the previous benchmark approval, corpus
fingerprint, and baseline. The repaired lexical development run reports:

| Metric | Final four | Candidate pool (top 20) |
|---|---:|---:|
| Required-evidence recall | 0.8333 | 0.9470 |
| Answerable evidence recall | 0.8226 | 0.9435 |
| Critical evidence recall | 0.7273 | 0.9091 |
| Precision | 0.2500 | diagnostic only |
| nDCG | 0.6825 | diagnostic only |

These numbers are retrieval-only. They are not comparable as a
retriever improvement against the old baseline because the evidence labels and
corpus changed. They are the approved repaired lexical baseline.

## Review gate

`rag_benchmark_review.md` contains every changed case, every critical
development case, and two PA12 continuity cases (20 total). The user accepted
all 20 and the matching approval hash is recorded. A same-source unmatched-hit
diagnostic supplies review leads but never awards relevance credit automatically.
