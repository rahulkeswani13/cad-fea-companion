# Features.md — Feature Talking Scripts (interview prep)

One 3–5 minute spoken script per shipped feature: what problem it solves, what
I built, the tradeoffs I chose, and exactly how it's verified (tests, evals,
demo prompts). This is **not** the demo script (`demo/DEMO_SCRIPT.md` is the
live product demo) — this file is for *my understanding and interview prep*.

**Convention going forward:** every feature that lands (F03, F04, …) gets a
section here with the same skeleton — Pitch · Script · Tests · Evals · Demo
prompts · Likely interview questions.

---

## F01 — Agent engineering foundation (AGENTS.md + ADR journal)

**Pitch:** Before writing feature code, I put agent-engineering guardrails in
place: a contribution policy for humans *and* coding agents, and an
architecture-decision-record journal so every contract change is deliberate.

**Script (~2 min):** "The first thing I built wasn't a feature — it was the
rules of the road. AGENTS.md encodes four policies that shape everything
after: additive-first change (never break an existing tool caller without an
ADR), tool results must flow through an outcome contract, solver honesty
(every answer states its method — CalculiX, surrogate, or analytical — mesh
size, and what was *not* verified), and every feature ships with unit tests
plus eval cases plus an ADR when a decision was made. The ADR journal
(`docs/adr/ADR-001`) records the big scoping calls: evolve this repo instead
of forking vibecad's 14,600-file C++ codebase; target the structural
simulation AI role; brake pedal stays the onboarding/eval part while two
flagship parts carry the demo; new physics comes from FreeCAD's own 74
headless FEM examples rather than invented solver plumbing. In interviews
this is my answer to 'how do you keep an LLM agent codebase from rotting' —
you treat tool contracts like APIs and make every change to them a recorded
decision."

**Tests/evals:** none directly (it's process), but it defines the gates every
later feature must pass: `pytest tests/ -q` and `eval/run_eval.py`.

**Demo prompt:** `cat AGENTS.md docs/adr/ADR-001-scope-and-architecture.md` —
walk the four policies and the six ADR-001 decisions.

---

## F02 — Tool outcome envelope (one error, one correction, receipts)

**Pitch:** Every tool result the LLM sees now flows through one envelope in
`companion/tools/outcome.py`: compact payloads, machine-readable failure
classes with exactly one concrete correction, receipts (tool, elapsed, what
changed), and zero raw tracebacks in context — raw diagnostics go to a debug
log on disk with a `debug_ref` pointer instead.

**Script (~4 min):**
"The problem I started with was that my tools returned ad-hoc dicts, and
three separate paths leaked raw junk into the model's context. FreeCAD scripts
embedded full Python tracebacks into the `error` field. The subprocess wrapper
attached 2,000-character stdout and stderr tails to failures. And the agent
graph serialized the entire result dict straight into the ToolMessage. On top
of that, my stress-query tool returned the same KPIs three times in one
message, and the system prompt re-serialized the full CAD state every single
turn. For an agent, that's not cosmetic — context pollution and
unactionable errors directly degrade tool-use quality.

So I built a single outcome envelope module with one job: shape what the LLM
sees. Four design decisions are worth defending:

First, **flat-additive, not nested**. The obvious design is
`{ok, data, error, correction}` with everything nested under `data`. I
rejected it because four consumers pin today's top-level keys — the eval
runner, the test suite, the persisted-results reload path, and the graph's
state mirroring. Restructuring would break all four for zero benefit to the
model, and it would violate my own additive-first policy. So the envelope
keeps every existing key at top level and only *adds* fields: a `receipt`
always; `error_class` and `correction` on failure; `debug_ref` when raw output
was moved to the log. Compactness comes from stripping bloat, not from
restructuring.

Second, **one choke point**. The envelope is applied in `call_tool`, the
single dispatcher every path funnels through — LLM tool calls, the heuristic
router, the eval runner, the HTTP API. Ten tools didn't need ten wrappers; one
wrapper means future tools inherit the contract for free, and it also gave me
a place to make unexpected exceptions become structured `internal_error`
results instead of crashing the graph node.

Third, **a small failure taxonomy with one correction each** — eleven classes
like `bad_params`, `no_geometry`, `freecad_timeout`, `mesh_failed`. The design
rule is 'one error, one concrete correction' — never a list of maybes,
because the point is to make the agent's *next action* obvious. The
repair-loop feature later extends this table; the contract is ready for it.

Fourth, **raw diagnostics go to disk, not chat**. Tails and tracebacks have
real debugging value, so deleting them would cost me root-cause analysis — a
job requirement. Instead they're appended to a debug log under
`data/workspace/logs/` and referenced by `debug_ref`. The LLM context stays
clean; the human keeps the forensic trail.

Receipts are deliberately minimal: tool name, elapsed seconds, and what
changed in session state (`geometry_replaced`, `results_replaced`). I decided
against a units map — units are already encoded in key names like
`_mm` and `_mpa` — and against duplicating KPIs into the receipt. Alongside
this I compacted the system-prompt CAD blob to a KPI-only summary, which was
actually the biggest single context reduction.

Verification: 23 new unit tests cover both envelope shapes, the classifier,
exception capture, and a literal 'no Traceback substring in any serialized
result' assertion. Three new eval cases assert correction and receipt fields
end-to-end through the real dispatcher, and I extended the eval runner with
`expect_error_class` / `expect_correction` / `expect_receipt` checks. Full
suite: 66 passing."

**Tests (`tests/test_outcome.py`, 23 tests, all memory-only — zero FreeCAD processes):**
- `test_success_envelope_has_receipt_and_domain_keys` — receipt + flat-additive keys on a brake-pedal create
- `test_observation_tool_receipt_changed_empty` — read-only tools report no state change
- `test_unknown_tool_failure_shape`, `test_bad_params_failure_shape`, `test_no_geometry_failure_shape`, `test_no_results_failure_shape` — one class + one correction per failure
- `test_envelope_strips_raw_diagnostics` — tails/traceback → `debug_ref`, single-line error, no junk in serialized JSON
- `test_envelope_condenses_long_freecad_error_on_success`
- `test_wrap_catches_exceptions_without_traceback` — tool crash becomes `internal_error`
- `test_hitl_cancelled_envelope` — human-rejected tool run carries `user_cancelled` + correction
- `test_envelope_is_flat_additive`, `test_classify_error` (10 cases), `test_cad_state_blob_is_compact_kpi_summary`, `test_cad_state_blob_empty_is_none_marker`

**Evals (`eval/cases.json`):** `f02_unknown_tool_correction`,
`f02_bad_web_type_correction` (bad web type → `bad_params` + correction +
receipt), `f02_success_receipt` (brake-pedal create → receipt). Runner
extension in `eval/run_eval.py`.

**Demo prompts (brake pedal only; GUI allowed for brake pedal, `open_gui: false` keeps it headless):**
```bash
# 1. Success receipt + flat KPIs
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; print(json.dumps(call_tool('create_brake_pedal', {'web_type':'xtruss','open_gui':False}), indent=2)[:600])"
# → receipt: {tool, elapsed_s, changed:['geometry_replaced']}; no error fields.

# 2. One error + one concrete correction
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; print(json.dumps(call_tool('create_brake_pedal', {'web_type':'zigzag'}), indent=2))"
# → error_class: bad_params, correction: "Fix the reported parameter value and retry the same tool."

# 3. Wrong-order usage self-heals (agent reads the correction)
.venv/bin/python -c "from companion.tools.cad_fea import reset_cad_sessions, call_tool; \
reset_cad_sessions(); import json; print(json.dumps(call_tool('get_max_von_mises', {}), indent=2))"
# → error_class: no_results, correction: "Call apply_load_and_solve first, then retry the query."

# 4. Debug log instead of context pollution (forced failure)
.venv/bin/python -c "from companion.tools import outcome; import json; \
print(json.dumps(outcome.envelope({'ok': False, 'error': 'Traceback (most recent call last):\n  File x.py\nValueError: boom', 'stdout_tail': 'x'*4000}, tool='demo', elapsed_s=0.1), indent=2))"
# → single-line error, debug_ref → data/workspace/logs/tool_debug.log
```

**Likely interview questions:**
- *Why not a nested `{ok, data, …}` envelope?* — breaks four consumers, violates additive-first, buys nothing for the model; compaction ≠ restructuring.
- *Why central wrapping instead of decorators on each tool?* — one enforcement point; timing and changed-detection come free; future tools inherit it.
- *How do you keep debuggability without tracebacks in context?* — disk log + `debug_ref`; the model gets the class + correction, the human gets the forensic trail.
- *What did this fix concretely?* — three live leak paths closed; KPI triplication removed; per-turn system-prompt state cut to a KPI summary; tools can no longer crash the graph node.

**Ops lesson (learned the hard way):** the FreeCAD GUI launcher is
fire-and-forget (`subprocess.Popen`), so agent-path tests with default
`open_gui=true` can silently accumulate GUI instances and swamp a laptop.
Gate runs now suppress GUI; test discipline: brake-pedal-only, memory-only
(`find_freecad_cmd → None`) unless a test explicitly needs FreeCAD, and
`pgrep`/`pkill -f FreeCAD.app` after any run that launches it.

---

## F03 — Pre-mesh B-Rep validation gate

**Pitch:** Invalid geometry now fails in seconds with a named stage and a
concrete correction — *before* Gmsh ever runs — via a two-layer gate in
`companion/tools/validate.py`: a host-side param gate (deterministic, no
FreeCAD needed) and a FreeCAD-side B-Rep check injected into all four
generator scripts (`isValid()`, volume, bbox; measured-vs-expected plausibility).

**Script (~4 min):**
"Before this feature, bad geometry was discovered the expensive way. The only
B-Rep check was a final `isValid()` at the very end of the build, and if
anything slipped past it, you found out when Gmsh or CalculiX crashed minutes
later, with a traceback and no hint of which stage failed. For an agent, that's
the worst possible failure mode: slow, unclassifiable, and unactionable.

F03 adds a validation gate with two layers. The host layer runs before
FreeCAD is even launched — it rejects degenerate parameters like a
zero strut radius, negative cell size, or NaN dimensions. The check uses the
`not (value > 0)` idiom, which catches NaN for free because every NaN
comparison is false. That layer is pure Python, so it's deterministic and
testable with zero FreeCAD installed.

The second layer runs inside the generated FreeCAD scripts, right after the
solid is built and recomputed, and before any export or meshing. It checks the
B-Rep itself: shape non-null, `isValid()`, positive finite volume, non-degenerate
bounding box. A key design decision is the hard/soft split. The structural
checks block, but plausibility checks — measured volume versus the host's
independent analytic estimate, relative density bounds — only *warn*. I did
that deliberately: boolean operations on lattices make exact volume ratios
fuzzy, and a false positive that blocks a live demo is worse than a soft
warning. Blocking is reserved for things that are certainly broken.

Failures report a named stage — `params_nonpositive`, `shape_null`,
`brep_invalid`, `volume_nonpositive`, `bbox_degenerate` — with the raw check
values including OCC error strings, and they map onto the F02 envelope as a
new `geometry_invalid` error class with one concrete correction. Successes
carry the validation block too, so every geometry result now proves it was
checked. The stage names live on one axis and the error class stays coarse —
the agent reasons with the class, the human debugs with the stage.

Two implementation details worth mentioning. First, the gate early-exits the
script by printing the JSON marker, flushing stdout, and raising SystemExit —
and the flush is load-bearing: my null-shape probe test caught that
FreeCADCmd's embedded interpreter can silently drop buffered stdout on
SystemExit, which would have made the gate look like a crash. That's exactly
why I wrote the probe. Second, SystemExit is a BaseException, so the script's
catch-all `except Exception` doesn't swallow it.

Verification is layered the same way the gate is: nine memory-only unit tests
cover the host gate, the classifier, and — my favorite — compile every
generated script and assert by character position that the gate call precedes
`Part.export` and `makeMeshGmsh`, so the gate can't silently drift after the
mesh. Two probe tests run headless when FreeCAD exists: one feeds a null shape
straight into the snippet and asserts the `brep_invalid` payload; the other
builds a real brake pedal and asserts `stage: passed` with `is_valid: true`.
The eval case is deterministic in both FreeCAD and fallback modes because the
host gate fires first."

**Tests (`tests/test_validate.py`, 11 tests; core 9 are memory-only, 2 probes skipif FreeCADCmd):**
- `test_nonpositive_strut_rejected_before_freecad`, `test_nan_cell_size_rejected` — host gate via the real dispatcher: `geometry_invalid` + `params_nonpositive` + correction + receipt
- `test_generic_param_gate_reports_only_bad_values`, `test_valid_params_pass_host_gate` — validator unit tests (NaN/negative/bad-names)
- `test_classify_geometry_invalid` — envelope classifier + correction table
- `test_snippet_contains_hard_stages`, `test_generated_scripts_compile` — snippet content + all six generated scripts compile
- `test_pedal_scripts_gate_before_export_and_gmsh`, `test_mount_scripts_gate_wired` — gate ordered before export/Gmsh by string position; success payloads carry `validation`
- `test_gate_fires_on_invalid_brep_headless` (probe: null shape → `brep_invalid`, no Gmsh, found the stdout-flush bug)
- `test_valid_pedal_reports_passed_stage_headless` (probe: real brake-pedal create → `stage: passed`, `is_valid: true`)

**Evals (`eval/cases.json`):** `f03_nonpositive_strut_rejected` — create_brake_pedal with `strut_radius_mm: 0` → `expect_ok: false`, `expect_error_class: "geometry_invalid"`, `expect_correction: true`, `expect_validation_stage: "params_nonpositive"`, `expect_receipt: true`. Runner gained the `expect_validation_stage` check.

**Demo prompts (brake pedal only; first two are FreeCAD-free):**
```bash
# 1. Host gate: degenerate param fails before FreeCAD launches (instant)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; print(json.dumps(call_tool('create_brake_pedal', {'web_type':'xtruss','strut_radius_mm':0}), indent=2))"
# → error_class: geometry_invalid, validation.stage: params_nonpositive, one concrete correction.

# 2. NaN dimension also caught (host gate idiom)
.venv/bin/python -c "from companion.tools.validate import validate_geometry_payload as v; \
import json, math; print(json.dumps(v({'cell_size_mm': math.nan, 'strut_radius_mm': 2.5})))"

# 3. Live gate on a real build: validation block on success (headless, ~8 s)
.venv/bin/python -c "from companion.tools.cad_fea import create_brake_pedal; \
import json; r = create_brake_pedal(web_type='xtruss', open_gui=False); \
print(json.dumps(r['validation'], indent=2)[:400])"
# → stage: passed, checks: {is_valid: true, volume_mm3, bbox_dims_mm, volume_vs_estimate}, warnings: []

# 4. Show the gate sits before meshing in the generated solve script (string positions)
.venv/bin/python -c "from companion.tools.brake_pedal import build_fem_script; \
s = build_fem_script('xtruss', 15, 2.5, 500, 5, 'f.FCStd'); \
print('gate at', s.index('_vstage'), '< mesh at', s.index('makeMeshGmsh'))"
```

**Likely interview questions:**
- *Why check before meshing instead of trusting solver errors?* — meshing is the expensive step and solver crashes are unclassifiable; fail-fast converts minutes of wasted compute into a seconds-scale named failure (R6 root-cause thinking).
- *How do you avoid false positives blocking good parts?* — hard checks only for certainly-broken geometry; plausibility ratios warn, never block.
- *How did you test code that runs inside another interpreter?* — three layers: pure host tests, compile-and-assert-ordering on the generated script text, and skipif headless probes that run the real snippet (the probe found the stdout-flush-on-SystemExit bug).
- *Relation to the outcome envelope?* — F03 is a producer of structured failures; F02's envelope is the transport. New stage names need no envelope changes, only one new error class.


---

## F04 — Design program layer (persisted params, revision hash, transactional edits)

**Pitch:** Every parametric part now has a *design program* — a persisted,
edited-in-place source of truth at `data/workspace/<part>_program.json` with
editable params, read-only fixed constants, a monotonic `rev`, and a
`params_hash` (sha256 over canonical JSON). "Set cell size to 12" is one
`update_design_program` call: merge over current params, hard-reject
preflight on ranges, rebuild through the existing create path, commit the new
revision only on success. A failed rebuild leaves the accepted revision
untouched on disk.

**Script (~4 min):**
"Before F04, the design lived in chat-thread memory only. Restart the app and
the current design is gone; change one parameter and the agent has to
reconstruct the whole create call; and a failed rebuild left session state
ambiguous. F04 makes the parametric part a persisted, transactional object.

The design program is a small JSON file per part: the editable params — web
type, cell size, strut radius, or cantilever length-width-height — the
read-only fixed constants listed for completeness so the program fully
describes the part, a monotonic revision integer, and a params hash: sha256
over the canonical JSON of the params, with numbers coerced to float so the
integer 12 from a tool call and 12.0 round-tripped from disk hash
identically. The hash is the design's identity; the rev counts accepted
commits.

The interesting decision is the transaction model. `update_design_program`
merges the requested changes over the current params, runs a range preflight
that hard-rejects — it never clamps, because silently building a different
part than the user asked for violates solver honesty — then delegates the
rebuild to the existing create function. Delegation matters: the create path
already owns the F03 validation gate, FreeCAD dispatch, fallbacks, and
session update, so the update path is a thin wrapper, not a parallel
pipeline. On success the program commits; on any hard failure — bad range,
validation gate, FreeCAD crash — nothing touches the file and the failure
envelope echoes what was attempted plus the preserved revision. One nuance I
chose deliberately: FreeCAD being *absent* is a degradation, not a failure —
the create path's memory-geometry fallback still commits the program with a
warning, because the params are still the accepted design.

Two behaviors fall out for free. A no-op update — including alias
normalization like bcc → xtruss collapsing to the current value — rebuilds
nothing, writes nothing, bumps nothing; in a live demo that saves a minute of
FreeCAD time. And every successful create seeds the program too, so there's
one source of truth no matter which path produced the geometry. Writes are
atomic — temp file plus rename — so a partial write can't clobber the
accepted revision. What I deliberately left out: no history array (per-run
records are F06's job), no revision-tagged filenames (rev rides inside
result payloads), no file locking (single-writer, documented), and analysis
params like force and mesh stay out of the program until F10 designs the
load-case schema properly.

Verification is 19 memory-only unit tests — no FreeCAD needed: hash
canonicalization, preflight and normalize rejects with the range named in
the correction, atomic roundtrip, create seeding, and the full update
transaction including failed-rebuild preservation, no-op, and dry-run — plus
five eval cases chained on a real brake-pedal create: read the program,
update cell size to 12, dry-run a strut change, no-op repeat, and an
out-of-range reject."

**Tests (`tests/test_design_program.py`, 19 tests, all memory-only):**
- `test_defaults_are_in_range_for_every_part`, `test_params_hash_is_canonical` — specs sanity; int/float and key-order-insensitive hashing
- `test_preflight_rejects_out_of_range_with_named_range`, `test_preflight_rejects_nan` — hard reject, range named in correction, NaN caught by comparison idiom
- `test_normalize_changes_aliases_coerces_and_rejects` — bcc→xtruss alias, string→float coercion, fixed-constant / unknown-param / bad-web-type rejects
- `test_save_load_roundtrip_and_rev_bump` — atomic write (no .tmp leftover), rev increments
- `test_create_seeds_program_with_memory_geometry`, `test_failed_create_does_not_touch_program` — real create path with FreeCAD absent; failed create preserves the file
- `test_get_lists_programs_when_nothing_active`, `test_get_returns_active_part_program`, `test_get_unknown_part_rejected`
- `test_update_cell_size_rebuilds_without_recreate` — one rebuild with merged params, rev bumped, hash matches file
- `test_failed_rebuild_preserves_accepted_revision` — stubbed gate failure: file byte-identical, `attempted_changes` + `program_preserved` in the envelope
- `test_noop_update_skips_rebuild_and_write` — incl. alias no-op (bcc → xtruss)
- `test_dry_run_previews_without_committing`, `test_out_of_range_update_never_rebuilds`, `test_update_rejects_non_dict_changes`, `test_call_tool_envelopes_program_tools`

**Evals (`eval/cases.json`):** `f04_get_program_after_create` (read the
seeded program), `f04_update_cell_size` (the flagship edit+rebuild),
`f04_update_dry_run`, `f04_update_noop`, `f04_update_out_of_range`
(`bad_params` + correction). Deterministic with and without FreeCAD via the
fallback path.

**Demo prompts (first is FreeCAD-free):**
```bash
# 1. Read the program after any create (instant)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; print(json.dumps(call_tool('get_design_program', {}), indent=2)[:600])"

# 2. The flagship edit: set cell size to 12, rebuild, commit (headless, ~8 s)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; r = call_tool('update_design_program', {'changes': {'cell_size_mm': 12}, 'open_gui': False}); \
print(json.dumps({k: r.get(k) for k in ('ok','changed','program')}, indent=2))"

# 3. Failed rebuild keeps the accepted revision: out-of-range reject (instant)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; r = call_tool('update_design_program', {'changes': {'cell_size_mm': 0.5}}); \
print(json.dumps({k: r.get(k) for k in ('ok','error','error_class','correction')}, indent=2))"

# 4. Inspect the persisted source of truth on disk
cat data/workspace/brake_pedal_program.json
```

**Likely interview questions:**
- *Why delegate the rebuild instead of a dedicated rebuild pipeline?* — one code path owns gating, fallbacks, and session update; a second pipeline doubles the surface F02/F03 have to cover. The wrapper is ~50 lines.
- *Why never clamp out-of-range params?* — the user asked for a specific design; silently building a different one is the dishonest failure mode. One error + one concrete correction is the contract.
- *Hash vs revision number — why both?* — the hash is content identity (works across machines and runs); the rev is human-readable ordering of accepted commits. Neither alone gives both.
- *What happens on a failed rebuild?* — nothing touches the disk (atomic write anyway), and the failure envelope carries `attempted_changes` + `program_preserved` so the agent knows exactly what state the world is in.
- *Why no history?* — scope discipline: per-run history is F06 (result querying) and F11 (async ops); the program is the *current accepted design*, not a journal.

---

> **F05 (frozen workbench) was skipped** — ADR-005: the no-geometry guard
> already lives at the tool-call boundary via the F02 envelope correction, so
> per-turn tool filtering bought nothing until F17 raises the stakes. No
> talking script for a feature that doesn't exist.

---

## F06 — Run history + `query_results` (per-run solve records)

**Pitch:** Every solve now leaves a permanent, queryable record: append-only
`data/workspace/<part>_runs.jsonl` (one line per solve, fallback runs
included and honestly flagged), a sortable `run_id` shared by the solve
payload, the stored record, and the new `query_results` tool — which also
answers "where is stress concentrated" via peak-node capture in the pedal
FEM script (`max_vm_location_mm`, live-verified at (18.4, 100.0, 10.4) mm).

**Script (~3 min):**
"Before F06, solves were fire-and-forget. The latest result lived in the
chat-thread session, the workspace JSON was overwritten on every solve, and
there was no run identity — so 'what changed between runs' and 'where is the
stress peak' had no stored answer. F06 makes every solve a first-class
record.

Three decisions are worth defending. First, storage is an append-only JSONL
file per part, not a database. At demo scale a rotation-free append-only log
is one `open('a')` call, survives restarts, and is shared across chat threads
exactly like the design programs — SQLite earns its keep when F11's async
operations arrive, not before. Second, every solve invocation is recorded,
including fallback and precomputed ones, with the method flag doing the
honesty work: the record says `calculix_ccx` or `precomputed_demo_estimate`,
so a scaled demo KPI can never masquerade as a live solve. Recording degrades
to a `history_write_error` warning key and can never fail a successful
solve — the same bookkeeping-never-breaks-the-answer rule as F04's program
writes. Third, the peak-stress location is captured inside the FreeCAD FEM
script by mapping the result object's von Mises array onto mesh node ids and
reporting the argmax node's coordinates — best-effort, `null` when the
result can't be mapped, which is exactly the runs that have no mesh.

What I deliberately did *not* capture: reaction forces. CCX only emits them
through the `.dat` file with an input-deck tweak — a parsing rabbit hole for
marginal value until F10 makes boundary conditions program params.
`query_results` says 'reactions: not captured' rather than returning blanks,
per the solver-honesty rule. And `query_results` itself does no natural
language parsing: `{part?, run_id?, last_n?}`, latest run in full plus
compact newest-first rows; 'where is stress concentrated' is the agent
reading `max_vm_location_mm`. I also registered it at all three tool
registration points — TOOL_SPECS, the dispatcher, and the LangChain tool
list — fixing the asymmetry where F04's program tools only exist at two of
three and the LLM path can't call them.

Verification: 12 memory-only tests (zero FreeCAD), including corrupt-line
tolerance on reads, OSError degradation, and a full fallback-path
integration test that creates, solves, and queries through the real
dispatcher. Four tool evals plus one agent eval, all deterministic with and
without FreeCAD. And a live pedal solve on this machine: 23.7 MPa at
(18.4, 100.0, 10.4) mm recorded, queried back by run_id."

**Tests (`tests/test_run_history.py`, 12 tests, all memory-only):**
- `test_record_run_stamps_result_and_appends` — run_id format, payload stamping, record fields incl. expected/ratio from F07's block
- `test_record_run_skips_failures_and_degrades_on_oserror` — failed solves never recorded; disk errors become `history_write_error`, never exceptions
- `test_read_runs_tails_and_skips_corrupt_lines` — tail-limited reads tolerant of hand-edited/corrupt lines
- `test_find_run_searches_all_parts` — run_id lookup across parts
- `test_query_results_unknown_part_is_bad_params`, `test_query_results_unknown_run_id_is_no_results`, `test_query_results_no_active_part_is_no_results` — error classes + corrections through the envelope
- `test_query_results_latest_then_by_run_id` — newest-first rows, `max_vm_location_mm` surfaced, `reactions: not captured`
- `test_query_results_part_with_no_runs` — per-part empty history
- `test_solve_records_run_and_estimate` — full integration on the fallback branch: create → solve → run_id + `expected_vs_actual` on the payload, program rev in the record, query roundtrip

**Evals (`eval/cases.json`):** `f06_solve_pedal_records_run` (solve →
`run_id` + `expected_vs_actual` fields), `f06_query_results_latest`,
`f06_query_results_bad_run_id` (`no_results` + correction),
`f06_query_results_unknown_part` (`bad_params`),
`agent_where_stress_concentrated` (agent picks `query_results`). Runner
gained the `expect_fields` check.

**Demo prompts (brake pedal only; solves pass `open_gui: false`):**
```bash
# 1. Solve once, then ask where the stress is (headless, ~1 min with FreeCAD)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool, reset_cad_sessions; \
reset_cad_sessions(); call_tool('create_brake_pedal', {'web_type':'xtruss','open_gui':False}); \
import json; print(json.dumps(call_tool('apply_load_and_solve', {'open_gui':False})['expected_vs_actual'], indent=2))"

# 2. Query history: latest run + recent rows (instant)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; r = call_tool('query_results', {}); \
print(json.dumps({'latest': {k: r['latest'].get(k) for k in ('run_id','method','max_von_mises_mpa','max_vm_location_mm','program_rev')}, 'runs': r['runs'][:3]}, indent=2))"

# 3. The raw append-only record
tail -2 data/workspace/brake_pedal_runs.jsonl | python3 -m json.tool --json-lines

# 4. Agent phrasing: "Where is the stress concentrated in the brake pedal right now?"
```

**Likely interview questions:**
- *JSONL per part vs SQLite?* — append-only log is restart-proof, thread-shared, one syscall; a DB is F11's call when async operations need cursors and cancellation state.
- *Why record fallback runs at all?* — the method flag keeps the record honest; excluding them would hide which answers were demo KPIs, the opposite of solver honesty.
- *How do you get the stress location out of FreeCAD?* — argmax over the result object's von Mises list, mapped to node ids via `NodeNumbers` (sorted-id fallback), coordinates from the FEM mesh; null when unmappable.
- *Why no reactions?* — CCX emits them only via `.dat` with an input-deck change; deferring to F10 (when BCs become params) is the honest scope call, and the tool says so.

---

## F07 — Pre-flight analytical estimates (expected vs actual)

**Pitch:** Every solve now carries an `expected_vs_actual` block: a closed-form
beam idealization computed from the part's own design constants, compared
against the returned max von Mises with a ratio and a divergence flag
(outside [0.33, 3.0] → flagged). Annotate-only — it never blocks or rewrites
a result. `companion/tools/estimate.py` is pure Python: no FreeCAD, no
session state, reusable for F08's convergence checks.

**Script (~3 min):**
"Before F07, only the cantilever had a closed-form reference — the pedal
solved with no expectation to judge the result against, so a mesh
artifact or setup error would surface as a confident-looking number. The fix
isn't a solver, it's discipline: before judging every solve, state what
physics says it should roughly be.

Each part gets a beam idealization with its assumptions written into the
payload. The brake pedal is an overhang cantilever from the clevis ring —
L about 122 mm, a 36-by-15 section, roughly 45 MPa at 500 N — deliberately
conservative because the real part also hangs off the pivot. The cantilever
reuses the Euler-Bernoulli reference, cross-checked
equal by a test so the two implementations can't drift. And these are
calibrated, not guessed: live CalculiX on the pedal gives 23.6 MPa — ratio
0.52 — comfortably in band.

The two design calls I'd defend hardest. First, the divergence band is
[0.33, 3.0] — deliberately loose, because beam idealizations of real
brackets are legitimately off by that much: stress concentrations at holes,
coarse linear tets under-predicting bending peaks. A tight band would fire
constant false alarms and get ignored; the flag's job is to prompt a re-check
of mesh and assumptions, not to prove either number wrong. Second, it
annotates only — never blocks, never rewrites. Lattice variants compare
against the solid-section estimate with an explicit caveat key, and a
missing or non-finite actual keeps the expected value and sets the ratio to
null instead of guessing. That's the solver-honesty rule applied to my own
hand calc.

One structural choice pays off later: the estimate module is pure — no
FreeCAD imports, no session reads — so F08's convergence study can reuse the
same expected values to judge whether mesh refinement is converging toward
physics, not just toward itself. The block is attached before results are
persisted, so F06's run records carry expected, ratio, and flag per run:
the history doubles as a divergence log."

**Tests (`tests/test_estimate.py`, 7 tests):**
- `test_brake_pedal_estimate_value` (≈45.06 MPa at 500 N) — idealization pinned
- `test_cantilever_estimate_matches_analytical_reference` — cross-check vs `analytical_cantilever_stress`, the drift guard
- `test_expected_vs_actual_band_and_flag` — in-band no flag (ratio 0.52), 6.7× and 0.04× flagged
- `test_caveat_present_for_lattice_absent_for_solid` — explicit lattice caveat
- `test_missing_actual_keeps_expected_without_flag` — nulls, never guesses
- `test_unknown_part_returns_none`, `test_cantilever_expected_vs_actual_block` — full block shape (expected 120, ratio 1.0, no flag)

**Evals (`eval/cases.json`):** rides `f06_solve_pedal_records_run`, which
asserts `expected_vs_actual` on every solve — the point is that no solve can
ship without its expectation attached.

**Demo prompts (brake pedal only):**
```bash
# 1. Solve and read the expectation block (headless with FreeCAD, instant on fallback)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool, reset_cad_sessions; \
reset_cad_sessions(); call_tool('create_brake_pedal', {'web_type':'xtruss','open_gui':False}); \
import json; print(json.dumps(call_tool('apply_load_and_solve', {'open_gui':False})['expected_vs_actual'], indent=2))"
# → expected 45.06, actual ~23.7, ratio ~0.53, divergence_flag: false, assumptions + caveat strings

# 2. Pure module, no FreeCAD at all: force the flag to fire
.venv/bin/python -c "from companion.tools.estimate import expected_vs_actual; \
import json; geo = {'part':'brake_pedal','web_type':'xtruss'}; \
print(json.dumps(expected_vs_actual('brake_pedal', geo, 500.0, 300.0)['divergence_flag']))"
# → true (6.7x expected): "re-check mesh and idealization assumptions"

# 3. See the assumptions your number is judged against
.venv/bin/python -c "from companion.tools.estimate import brake_pedal_expected_mpa; \
sigma, assumptions = brake_pedal_expected_mpa(500.0); print(round(sigma,2), 'MPa —', assumptions)"
```

**Likely interview questions:**
- *Why a 3× band?* — beam idealizations of holed, lattice, coarse-meshed brackets are legitimately off by that much; a tight band cries wolf and gets ignored. The flag prompts re-checking, it doesn't verdict.
- *Why annotate instead of block?* — solver honesty: the solve is the ground truth being reported, the estimate is the sanity check; inverting that relationship would let a hand calc veto a converged result.
- *Why compare lattices against a solid-section estimate?* — the idealization is a bound, and the caveat key says exactly that; a per-architecture lattice hand calc is a research project, not a pre-flight.
- *How did you pick the pedal idealization?* — nearest support (clevis) overhang bending with the connector-bar section; the pivot support makes it conservative, which the calibration confirms (FEA 0.52× expected, in band).

---

## Engine mount removal (ADR-008)

**Pitch:** Deleted the third demo part outright — module, tools, golden data,
docs, tests, evals — because it earned none of its per-turn token cost. The
part family is now cantilever (verification) + brake pedal (lattice) until
the UAV arm (F26) lands as the flagship.

**Script (~90 sec):**
"The mount was the least interesting part I had: its FEA is essentially
axial compression — my F07 pre-flight estimate for it was literally force
over area — and every lattice behavior it demonstrated, the pedal shows with
more drama. But it cost real tokens on every single turn: two tool specs in
the system prompt and two schemas in bind_tools, forever, for a part nobody
demoed. So I removed it as one recorded decision — AGENTS.md requires an ADR
before deleting public tool surface, which forced the question 'what breaks?'
The answer was 'nothing structural': the part dispatch is a branch, the
design program is table-driven, run history is part-keyed, and the router had
mount phrases I deleted. What I did *not* do is just delete the tests that
mentioned it — the eval cases became pedal equivalents so get_lattice_metrics
and compare_brake_pedal_variants kept their coverage, and the heuristic test
file kept its pedal routing tests under an honest name. The token budget I
freed up is roughly what the UAV arm tool will spend when F26 lands, so the
net prompt size stays flat while the demo story gets better."

**Verification:** full suite green after removal (pytest, eval, FreeCAD
smoke on pedal + cantilever); `grep -r engine_mount companion/ tests/ eval/`
returns nothing.

**Demo prompt:**
```bash
# The old tool is gone and says so cleanly
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; print(json.dumps(call_tool('create_engine_mount', {'web_type':'bcc'}), indent=2))"
# → error_class: unknown_tool, correction points at TOOL_SPECS
```

**Likely interview questions:**
- *Why delete instead of deprecate?* — additive-first protects *callers*;
  this was my own demo surface with no external users, and a dual-path
  deprecation of a part I never demo is process theater.
- *What did removal teach you about the architecture?* — that the parts are
  leaves: table-driven programs, part-keyed history, branch dispatch. F26's
  UAV arm slots in by adding a row, not by touching the spine.
- *Token math?* — two tool specs + two schemas gone from every prompt; the
  UAV arm's spec will roughly re-spend that, so prompt size stays flat
  while the demo improves.

---

## F08 — Mesh convergence study (`run_convergence_study`)

**Pitch:** "Is this number mesh-converged?" is now a tool call: 2–3 live
CalculiX solves at refining mesh sizes (default 1.0×/0.7×/0.5× ladder over
the part default), a compact per-mesh table (nodes, max von Mises,
deflection, % change, `run_id`), and a recommendation — the coarsest mesh
within 5% of the finest run. Setups whose "solve" can't vary with mesh (fcc
precomputed KPIs, FreeCAD absent) are refused up front instead of being
tabled as fake evidence.

**Script (~3 min):**
"Every FEA answer in this repo states its mesh size — F08 is the tool that
decides *which* mesh size deserves to be stated. The design was settled in a
grilling review before code, and four decisions are worth defending.

First, **live solves only**. The FCC pedal returns precomputed demo KPIs and
the no-FreeCAD path returns analytical fallbacks — identical at every mesh
size. A convergence table built from those numbers would be fabricated
evidence, which is worse than no table. So the tool refuses up front through
the F02 envelope — a new `unsupported_setup` class with one correction
pointing at xtruss/solid — and if a sub-run falls back mid-study, that mesh
is recorded as *failed*, never silently mixed into the verdict.

Second, **the verdict rule**: recommendation = the coarsest mesh whose max
von Mises sits within 5% of the finest run. Convergence is a purchasing
decision — why pay for 6,500 nodes if 1,200 buys the same number? I anchor
every mesh against the finest run rather than on successive differences
because two adjacent coarse meshes can agree while both are wrong; the
finest available answer is the only anchor I have. If nothing coarser
qualifies, the report says not-converged, offers the finest mesh as
best-available, and says refine-further — no Richardson extrapolation,
because a fit through three noisy points is theater, not evidence.

Third, **the ladder**: fixed multipliers of the part default (pedal
5/3.5/2.5 mm, cantilever 2.5/1.75/1.25) with an explicit `mesh_sizes_mm`
override. Geometry-aware ladders tied to strut radius or cell size wait for
F26's part family — that coupling isn't mine to guess yet.

Fourth, it's **synchronous and history-native**. Sub-runs go through
`apply_load_and_solve` with the GUI suppressed, so each is an ordinary F06
run-history record and the report cites `run_id`s — the study is auditable
after the fact, by run. A failed mesh makes the study `incomplete` (partial
report) rather than aborting silently; all-failed returns the last failure's
error class through the envelope. Async handles are F11's job, and the tool
description says plainly that it costs 2–3 solves.

Live verification on this machine: the cantilever at 2.5/1.75/1.25 mm gives
61.4 / 86.8 / 98.0 MPa in 5.8 s total — coarse linear tets under-predicting
the bending peak, climbing toward the 120 MPa Euler-Bernoulli reference —
and the tool says exactly that: not converged, refine further, 1.25 mm
best-available. That's the demo line: the tool argues with your mesh, not
for it."

**Tests (`tests/test_convergence.py`, 13 tests, all memory-only — zero
FreeCAD processes):**
- `test_no_geometry_refused` — `no_geometry` + correction through the envelope
- `test_fcc_refused_as_unsupported_setup`, `test_missing_freecad_refused` — the live-only gate, both refusal classes
- `test_mesh_ladder_default_multipliers` — pedal/cantilever ladders pinned
- `test_explicit_mesh_list_normalized_and_validated` — unsorted input → coarse→fine; five bad-list shapes → `bad_params`
- `test_converged_series_recommends_coarsest_within_tolerance` — verdict, run_id citation, % change, receipt, honesty note
- `test_not_converged_recommends_finest_with_refine_flag`
- `test_sub_runs_are_headless_and_force_passes_through` — `open_gui=False` on every sub-run
- `test_fallback_mid_study_marks_mesh_failed_and_incomplete` — a fallen-back finest mesh never joins the verdict
- `test_failed_mesh_reported_not_silent` — failure condensed (no traceback), study continues
- `test_single_success_gives_no_verdict` — `converged: null`, honest
- `test_all_meshes_fail_is_failure_envelope` — last failure's class carried out
- `test_router_routes_convergence_phrases` — heuristic router picks the tool

**Evals (`eval/cases.json`):** `f08_setup_fcc_pedal` +
`f08_convergence_fcc_refused` (deterministic in both FreeCAD and fallback
modes — the refusal fires before any solve) and `agent_mesh_convergence`
("is the mesh converged" routes the agent to the tool).

**Demo prompts (cantilever is the fast live path; solves are headless):**
```bash
# 1. Live study: watch coarse tets under-predict, tool says refine further (~6 s)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool, reset_cad_sessions; \
reset_cad_sessions(); call_tool('create_cantilever', {'open_gui': False}); \
import json; r = call_tool('run_convergence_study', {}); \
print(json.dumps({'runs': r['runs'], 'converged': r['converged'], \
'recommended_mesh_max_size_mm': r['recommended_mesh_max_size_mm'], 'verdict': r['verdict']}, indent=2))"

# 2. The honest refusal: fcc pedal KPIs cannot converge (instant after an fcc create)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; call_tool('create_brake_pedal', {'web_type': 'fcc', 'open_gui': False}); \
print(json.dumps(call_tool('run_convergence_study', {}), indent=2)[:700])"
# → error_class: unsupported_setup, correction points at xtruss/solid

# 3. Explicit mesh list override (2 sizes is a valid study)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; print(json.dumps(call_tool('run_convergence_study', {'mesh_sizes_mm': [4, 2.5]}), indent=2)[:700])"

# 4. Agent phrasing: "Is the current mesh converged? Run a mesh convergence study."
```

**Likely interview questions:**
- *Why refuse non-live setups instead of tabling whatever comes back?* — a table of mesh-invariant numbers is fabricated evidence; the refusal is a better demo moment than a flat column, and it's the solver-honesty rule applied to my own tool.
- *Why compare each mesh to the finest run, not successive differences?* — adjacent coarse meshes can agree while both are wrong; anchoring on the finest available answer matches the operational question ("can I trust the cheap run?").
- *Why recommend the coarsest within band?* — convergence is a purchasing decision; the cheapest mesh that buys the converged answer is the right default, and the report still shows every run.
- *Why no Richardson extrapolation?* — three points, linear tets, a stress peak that moves; a fitted extrapolation would add false precision, and the report already states what's not verified (local refinement at the peak).
- *What does it mutate?* — nothing durable except ordinary run-history records; mesh stays a per-call argument and the session ends on the finest run, exactly as if the solves were issued by hand.


## F09 — Material as parameter + selection guidance (`compare_materials`)

**Pitch:** "Compare Ti vs Al" is now a cited, physics-honest tool call — and
"switch the pedal to titanium" is a one-line design-program edit. Five
materials (Al 6061-T6, Al 7075-T6, Ti-6Al-4V, PA12, Steel-Generic) live in a
cited table (`data/materials.json`, mirrored as `docs/materials.md` for RAG
citations, drift-checked by a test). `compare_materials` scales the best
available run per material — stress carried over, deflection × E ratio, mass
× density ratio, SF vs *each* material's own yield — ranked lightest at
SF ≥ 1.5, every row carrying its sources. The PA12 row is included but its
scaled deflection is flagged `deflection_not_verified` (at E ≈ 1.8 GPa,
linear scaling leaves small-strain territory).

**Script (~3 min):**
"Material was hardcoded in six places — the pedal's Al constants baked into
its FreeCAD scripts, the cantilever's steel card, every fallback KPI, and the
variant comparison always judging SF against Al yield. F09 makes it a
parameter with three defensible choices.

First, **citations before embeddings**. The plan orders F09 before the
embedding-RAG feature, so 'RAG-grounded' can't mean retrieval yet — and
shouldn't. Every number the agent quotes comes from a five-row table where
each property traces to a source string (MatWeb, MMPDS, EOS, the FreeCAD
card). The same table is mirrored into `docs/materials.md`, which the
existing TF-IDF store ingests — so chat citations and tool citations are the
*same numbers*, and a unit test fails if the two ever drift. When embeddings
arrive, they wrap this table; they don't replace it.

Second, **material is a design-program parameter, not a side channel** —
enum-validated like `web_type`, so 'make it titanium' is
`update_design_program(changes={'material': 'ti6al4v'})`: alias resolution,
range-free validation, revision bump, rebuild with the new density and
modulus, and a failed rebuild still preserves the accepted revision. The one
contract touch — the cantilever's material moved from read-only fixed
constants to editable — is recorded in ADR-010, and per-part defaults keep
every pre-F09 caller byte-identical: default result strings are unchanged.

Third, **one solve, honest scaling — not five solves pretending to be free**.
`compare_materials` takes the best available base run — session solve, else
latest run-history record, else committed precomputed KPIs, else (pedal
only) the demo estimate, always labeled — and scales it linear-elastically:
stress is load-driven and carried over, deflection scales with the modulus
ratio, mass with density, and safety factor is judged against *each*
material's own yield. The method label says `scaled_from_calculix` or
`<base>_scaled`, and the not-verified note names what this *isn't*: fatigue,
temperature, as-built AM lattice allowables. PA12 is the interesting row —
mass and SF scale fine, but a linearly scaled polymer deflection is
small-strain math applied to a part that won't stay small-strain, so the row
ships with `deflection_not_verified` and the correction says run a live
solve. The ranking still works — lightest at SF ≥ 1.5 — and the recommendation
can be PA12 *with its flag on*, which is the honest version of 'nylon is
cheapest'.

Numbers from the fallback path (500 N, X-truss): Al 0.225 kg / SF 20 /
0.21 mm → Ti 0.368 kg / SF 64 / 0.127 mm — same stress, stiffer, stronger,
heavier: exactly the trade the table promises."

**Tests (`tests/test_materials.py`, 20 tests, all memory-only — zero
FreeCAD processes):**
- `test_table_loads_five_cited_materials` — five ids, sane physics, every property sourced
- `test_alias_resolution` — 'Ti-6Al-4V' / 'ti' / 'TI64' / 'nylon' / 's235' / rejects 'unobtainium'
- `test_bad_material_payload_names_every_option` — one error + one correction listing all five
- `test_default_descriptions_byte_identical` — pre-F09 result strings survive unchanged
- `test_docs_materials_md_stays_in_sync` — the RAG mirror cannot drift from the table
- `test_scale_result_to_titanium` — mass × ρ ratio, deflection × E ratio, SF vs 880 MPa, method label
- `test_scale_result_flags_pa12_deflection` — the NOT VERIFIED flag fires for polymers
- `test_scale_result_same_material_is_noop` — no phantom scaling for the reference material
- `test_create_pedal_with_material` / `test_create_rejects_unknown_material` — create path + envelope
- `test_update_program_switches_material` / `test_update_program_noop_same_material` / `test_update_program_rejects_unknown_material` — rev bump, no-op, program preserved on bad input
- `test_solve_follows_program_material` — solve uses the program's E/nu/density/yield (Ti deflection = Al × 69/113.8)
- `test_compare_materials_from_session` — 5 rows, labeled base, PA12 flag, mass-ranked recommendation, citations
- `test_compare_materials_refuses_cold_cantilever` — `no_results` + "solve first" instead of guessing
- `test_cantilever_analytical_uses_material_modulus` — closed-form deflection follows the table
- `test_cantilever_create_and_program_material` — cantilever default steel, material no longer fixed
- `test_compare_variants_uses_program_material_yield` — SF judged against Ti's 880 MPa when the program says Ti
- `test_legacy_program_self_heals_material` — pre-F09 program files upgrade on their next edit

**Evals (`eval/cases.json`):** `rag_materials_table` (Ti/PA12 properties
retrieved with ≥1 citation), `f09_compare_materials` (rows + recommendation +
citations), `f09_set_material_7075_dry_run` ('7075' alias → proposed revision),
`f09_unknown_material_rejected` (bad_params + correction + receipt).

**Demo prompts:**
```bash
# 1. The headline: "compare Ti vs Al" with citations (instant; scales stored runs)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; r = call_tool('compare_materials', {}); \
print(json.dumps({'base': r['base'], \
'recommendation': {k: r['recommendation'][k] for k in ('material','mass_kg','safety_factor_vs_yield')}, \
'rows': [{k: row[k] for k in ('material_id','mass_kg','safety_factor_vs_yield','deflection_mm','method')} for row in r['rows']]}, indent=2))"

# 2. "Switch the pedal to titanium" — program edit, rebuild, rev bump
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; print(json.dumps(call_tool('update_design_program', \
{'changes': {'material': 'Ti-6Al-4V'}, 'open_gui': False}), indent=1)[:600])"

# 3. The honest correction: an unknown material names every valid option
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; print(json.dumps(call_tool('create_brake_pedal', {'material': 'vibranium'}), indent=1)[:500])"

# 4. Agent phrasings: "What about titanium vs aluminum for this pedal?"
#    "Switch the bracket to 7075 and re-solve" / "Would printed nylon survive this load?"
```

**Likely interview questions:**
- *Why scale one solve instead of solving per material?* Stress in a
  load-driven linear-elastic setup is essentially E-independent; re-meshing
  five times buys noise, not signal. The scaling is labeled as an assumption
  and the row states what wasn't verified. When it matters (polymer
  deflection), the tool refuses to pretend.
- *Why does PA12 appear at all if you can't trust its deflection?* Mass and
  SF are usable; the flag is scoped to exactly the claim that's invalid.
  Banning the row would hide a real trade; faking the number would be worse.
- *Two sources of truth — JSON and the markdown doc?* The JSON computes; the
  md cites. A sync test pins every id, modulus, density, and yield across
  both, so the duplication is checked, not trusted.
- *Is 'RAG-grounded' overselling a lookup table?* Today it's exact-match
  retrieval over cited rows — which is what the honesty rules want. F15 adds
  embeddings over the same corpus; the citation contract doesn't change.
- *What about as-built AM allowables?* Deliberately out of scope: handbook
  bulk values + an explicit not-verified note, because inventing knockdown
  factors without build data would be fabricated precision.

---

## F26 — Flagship 1: UAV arm part family (`create_uav_arm`)

**Pitch:** A parametric quadcopter arm — root clamp boss, tapered arm, tip
motor-mount ring — with solid and X-truss variants, landing as the first
flagship demo part. The interesting engineering isn't the spine (it slots in
by adding a row, not touching it); it's the geometry architecture: solid
chord rails along the taper's top/bottom with the lattice web exposed on the
sides, and a mesh-sizing story that differs per variant because Gmsh chokes
on the lattice boolean.

**Script (~3 min):**
"The arm is the part that makes the demo look like real simulation-product
work: a 36×28×20 clamp boss with four M3 bolts, a tapered arm from 24×12 down
to 16×8 over a parametric 120–320 mm length, and a ⌀34 motor ring with four
M3 holes — solved as a cantilever under 120 N of motor thrust at the ring.

Three decisions I'd defend. First, the **chord-rail lattice architecture**.
The naive skin-enclosed lattice is invisible — it looks identical to solid,
which kills the demo. The bare open truss shows the X-pattern but leaves bumpy
sawtooth top and bottom surfaces. The landed design puts 1.5 mm solid rails
along the taper's top and bottom faces — smooth, load-bearing minimum
thickness — with the X-truss web exposed on the sides between them, struts
biting 0.5 mm into the rails for a clean fuse. Design-space discipline falls
out naturally: boss, ring, and rails are non-design; the tapered interior
between the rails is the design space. Mass goes 157 g solid → 130 g truss,
~−17%, with the stress story still honest (xtruss golden: 95 MPa, SF 2.9).

Second, the **strut floor at 1.5 mm** and mesh sizing per variant. Below
1.5 mm, Gmsh can't resolve the strut cross-section against the cell size —
so the design program hard-rejects it with the range named, never clamps.
And the variants need different meshes: the solid solves in seconds at
3.5 mm, but the same size on the xtruss boolean — rails plus dozens of strut
intersections — had Gmsh burning a single core for 30+ minutes. I killed it,
recorded the finding in ADR-011, and the lattice solves at ~5 mm. That also
surfaced a real spine bug: a hung solve orphaned its Gmsh child at 100% CPU,
so `run_freecad_python` now runs FreeCADCmd in its own process group and
kills the group on timeout.

Third, **goldens before fallbacks**. The solid JSON is a live CalculiX run —
44.6 MPa max von Mises at (218.4, 9.4, 4.0) mm, 1.69 mm tip deflection,
SF 6.2 at 120 N. The xtruss JSON is a calibrated fallback (130 g, 95 MPa,
SF 2.9, labeled `precomputed_demo_estimate` with `fallback: true`) because
the lattice boolean hung Gmsh at the solid mesh size. The no-FreeCAD path
scales from those base pairs and says so. The F07 pre-flight estimate
(tapered cantilever, root-section bending) lands at 40 MPa, ratio 1.11
against the solid golden — in band.

Everything else came free from the table-driven spine: design program row,
run-history key, router branch with a cantilever guard so 'drone arm'
doesn't misroute, compare_materials and precomputed-result ladders, F03 gate
with a plan-first expected bbox."

**Tests:** `tests/test_uav_arm.py` (16 tests, all memory-only — zero FreeCAD):
creates for both variants + bcc/truss aliases, invalid web_type reject,
defaults-preserving solve through the real dispatcher, precomputed loads,
golden-untouched rule (solve writes workspace, never `data/results/`),
generator API, arm_length propagation, volume/fill/bbox estimators, fallback
shape, get_max_von_mises round-trip. Plus five UAV routing tests in
`tests/test_pedal_heuristics.py` (solid/truss phrasing, drone/motor-mount
keywords, and the guard that UAV prompts never fall through to
create_cantilever).

**Evals (`eval/cases.json`):** `f26_create_uav_arm` (receipt), 
`f26_bad_web_type_uav_arm` (bad_params + correction + receipt),
`f26_update_uav_arm_cell_size` (program edit), `f26_solve_uav_arm_honesty`
(run_id + expected_vs_actual + SF fields), `f26_agent_uav_arm_demo`
(agent routes the demo prompt).

**Demo prompts:**
```bash
# 1. Solid arm (headless create, memory path instant; ~10 s with FreeCAD)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool, reset_cad_sessions; \
reset_cad_sessions(); import json; r = call_tool('create_uav_arm', {'web_type':'solid','open_gui':False}); \
print(json.dumps({k: r.get(k) for k in ('ok','web_type','mass_kg','relative_density')}, indent=2))"

# 2. Lattice arm — chord rails + exposed X-truss web
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; r = call_tool('update_design_program', {'changes':{'web_type':'xtruss'}, 'open_gui':False}); \
print(json.dumps({k: r.get(k) for k in ('ok','changed','program')}, indent=2))"

# 3. Solve with honesty block (120 N default, expected ~40 MPa vs golden 44.6)
.venv/bin/python -c "from companion.tools.cad_fea import call_tool; \
import json; r = call_tool('apply_load_and_solve', {'open_gui':False}); \
print(json.dumps({k: r.get(k) for k in ('method','max_von_mises_mpa','safety_factor_vs_yield','expected_vs_actual')}, indent=1)[:800])"

# 4. Agent phrasings: "Create a solid aluminum UAV arm and set up the 120 N tip load" /
#    "make the arm 220 mm long" / "where is the stress concentrated in the arm?"
```

**Likely interview questions:**
- *Why chord rails instead of a fully enclosed lattice?* — enclosed is
  invisible (demo-dead) and bare truss is bumpy; rails are the minimum
  surface-thickness requirement done structurally, and the rails are
  non-design like the boss and ring.
- *Why a 1.5 mm strut floor?* — meshability: below it Gmsh can't resolve the
  bar cross-section. The program rejects with the range named rather than
  clamping, because silently building a different part than asked is the
  dishonest failure mode.
- *Why only solid and xtruss?* — the pedal already demos fcc; a second
  lattice architecture on the arm spends schema tokens without a new story.
  Additive later if it earns it.
- *Mesh per variant?* — solid 3.5 mm solves in seconds; the xtruss boolean
  needs ~5 mm (3.5 hung Gmsh for 30+ min, documented in ADR-011). The FEM
  script's 25k-node guard bounds an over-fine request.
- *Where do the goldens come from?* — solid is a live CalculiX run in
  `data/results/`; xtruss is a calibrated fallback (Gmsh hung on the lattice
  boolean) labeled `precomputed_demo_estimate` with `fallback: true`.
