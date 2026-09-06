# Design programs and revisions

A design program is the persisted source of truth for one parametric part. The
generated CAD body and solve results are derived from it. Programs are stored as
`data/workspace/<part>_program.json`; this is runtime state and is not a design
artifact to edit by hand.

## What is editable

The three supported parts and their current editable parameters are:

| Part | Editable parameters and accepted range |
|---|---|
| `brake_pedal` | `web_type`: `solid`, `xtruss`, `fcc`; `cell_size_mm`: 5–40; `strut_radius_mm`: 1–5; `material` |
| `cantilever` | `length_mm`: 10–500; `width_mm`: 2–100; `height_mm`: 1–50; `material` |
| `uav_arm` | `web_type`: `solid`, `xtruss`; `arm_length_mm`: 120–320; `cell_size_mm`: 6–30; `strut_radius_mm`: 1.5–4; `material` |

Numeric limits are hard preflight limits: invalid, non-finite, or out-of-range
values are rejected and never clamped. Material values are normalized against
the ids and aliases in `docs/reference/materials.md`. Fixed geometry constants
are listed in the program response for context and cannot be changed through
`update_design_program`. Force, mesh size, and boundary conditions are analysis
inputs, not design-program parameters.

## Revision identity

Each accepted program has a monotonic integer `rev` and a 12-character
`params_hash`. The hash is the first 12 hex characters of SHA-256 over canonical
JSON for the editable parameters; numeric values are coerced to floats, so
`12` and `12.0` identify the same design. The file holds the current accepted
program only. Per-solve history is stored separately and carries the program
revision and hash used for that run.

`get_design_program` returns the active part's program, or lists on-disk programs
when no part is active. A part must first be seeded by its `create_*` tool before
it can be edited. `update_design_program` merges the requested changes, applies
normalization and preflight, rebuilds through the part's existing create path,
and commits only after success.

`dry_run=true` returns the proposed parameters, hash, and next revision without
rebuilding or committing. A normalized no-op returns `changed: false` and does
not rebuild or bump `rev`. A failed validation or rebuild returns the attempted
changes and preserves the accepted revision and hash. Successful writes use a
temporary file followed by an atomic replace. Program files are shared runtime
state; the implementation assumes a single writer.

Source and applicability: current behavior is defined by
`companion/tools/design_program.py`, `companion/tools/cad_fea.py`, and the
canonical ranges in `companion/tools/tool_schemas.py` (ADR-004, ADR-010,
ADR-013). Revision identity describes the program file, not a safety approval or
revision-tagged export filename.
