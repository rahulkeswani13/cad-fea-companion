# ADR-004: Design program layer (F04)

Date: 2026-08-16 · Status: accepted

## Context

Session state (`_SESSIONS` in `cad_fea.py`) was in-memory and per chat thread:
nothing survived a restart, and every design change meant a fresh
`create_*` call with a full parameter list the agent had to reconstruct.
There was no persisted "current design", no identity for a param set, and no
transactional guarantee — a failed rebuild left session state pointing at
whatever came before. The plan (F04) calls for persisted params + revision
hash per part, `get_design_program` / `update_design_program`, range
preflight, and failed-rebuild protection. Decisions were stress-tested in a
two-round design review before implementation.

## Decisions

1. **Parameter scope: the existing editable surface only.** Programs hold
   `web_type`, `cell_size_mm`, `strut_radius_mm` (lattice parts) or
   `length_mm`, `width_mm`, `height_mm` (cantilever). All other geometry
   constants are *listed* in the program as read-only `fixed` metadata
   (derived from the generator modules, so the listing cannot drift) and
   sending them in `changes` is rejected. Promoting new constants to editable
   params happens when a feature needs it (F26 UAV arm). Analysis params
   (force, mesh, BCs) are deliberately excluded — that schema is F10's.
2. **All three parts get programs.** Cantilever is nearly free and proves the
   layer is generic, not brake-pedal-shaped — which is what F26 inherits.
3. **Revision = monotonic `rev` integer + `params_hash`.** The hash is sha256
   (12 hex) over canonical JSON of the params, with numbers coerced to float
   so `12` from a tool call and `12.0` round-tripped from the file are the
   same design. `rev` bumps on every accepted commit; the hash is identity.
   No history array — the file holds the current accepted program only
   (per-run records are F06/F11).
4. **One global file per part** (`data/workspace/<part>_program.json`,
   gitignored runtime state), shared across chat threads; sessions keep only
   an "active part" pointer. No file locking — single-writer is a documented
   limitation.
5. **`update_design_program` = merge → preflight → rebuild → commit-on-success.**
   It delegates the rebuild to the existing `create_*` functions rather than
   a parallel pipeline — F03 gating, FreeCAD dispatch, fallbacks, session
   update, and program commit stay in one place. `dry_run=true` does preflight
   + hash preview only.
6. **Preflight hard-rejects, never clamps.** Out-of-range or NaN values fail
   as `error_class: bad_params` with one correction naming the valid range
   (`PARAM_SPECS` in `design_program.py` is the single source). Silent
   clamping would violate solver honesty.
7. **Failure boundary: hard failures never touch the file.** Range rejects,
   F03 gate failures, FreeCAD crash/timeout leave the accepted revision on
   disk untouched; the failure envelope echoes `attempted_changes` +
   `program_preserved` instead. A missing FreeCAD installation is a
   *degradation*, not a failure: the create path's memory-geometry fallback
   still commits the program, with its warning.
8. **Every successful `create_*` seeds/overwrites the program** (bump `rev`),
   so the program stays authoritative after any path. A no-op update
   (changes equal current params after alias normalization, e.g. `bcc` →
   `xtruss`) rebuilds nothing, writes nothing, bumps nothing, and returns
   `changed: false`.
9. **No revision-tagged filenames.** `rev`/`params_hash` ride inside result
   payloads (`program` key); renaming exports would ripple through
   `open_current_in_freecad` candidates and evals for zero demo value.
   Per-run artifacts are F06's job.
10. **Writes are atomic** (tmp + `os.replace`) so a partial write can never
    clobber the accepted revision. Agent-side heuristic routing for edit
    phrasings ("set cell size to 12") is deferred to F05's router work.

## Consequences

- "set cell size to 12" is one tool call that edits, rebuilds, and revalidates
  without recreating; a failed rebuild answers with the preserved revision.
- `get_design_program` with no active part inventories on-disk programs
  instead of failing (there is a useful answer), and points at the seeding
  `create_*` call.
- `update_design_program` carries an ensure-commit step after a successful
  rebuild: if the create path's own program write failed (OSError) or was
  stubbed in tests, the update commits the accepted params itself — after a
  successful update returns, the file hash always matches the built params.
- Verification: `tests/test_design_program.py` (19 memory-only tests: specs,
  hash canonicalization, preflight/normalize rejects, roundtrip + atomic
  write, create seeding, full update transaction incl. failed-rebuild
  preservation, no-op, dry-run, envelope receipts) and eval cases
  `f04_get_program_after_create`, `f04_update_cell_size`, `f04_update_dry_run`,
  `f04_update_noop`, `f04_update_out_of_range` (deterministic with and
  without FreeCAD via the fallback path).
