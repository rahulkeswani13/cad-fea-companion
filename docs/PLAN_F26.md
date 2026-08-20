> Historical — pre-implementation spec. Shipped mass is 157 g → 130 g; the 55–90 g band below is the old tuning target.

# Flagship 1 — UAV arm (F26), built on borrowed text-to-cad / vibecad rules

Scope per your choices: **F26 only** — `create_uav_arm` with solid/xtruss variants, STEP export, metrics, static 120 N solve, pre-flight estimate, design-program integration, tests, evals, ADR. F27 (modal/240 Hz) is explicitly deferred; the FEM script leaves a clean seam for it. Editable params: `web_type`, `arm_length_mm`, `cell_size_mm`, `strut_radius_mm`, `material`.

## Where each borrowed rule lands

| Borrowed rule (source) | How it lands in F26 |
|---|---|
| Plan-first: named params + expected bbox before building (text-to-cad `cad` skill) | `PARAM_SPECS["uav_arm"]` ranges + host-side pure-Python volume estimator feeds expected volume to the F03 gate; **additive** optional `expected_bbox_mm` warn-check in `validate.py` (default `None`, existing callers unchanged) |
| STEP = primary validated artifact; meshes derived (text-to-cad) | `build_geometry_script` gate-checks the B-Rep *before* export; STEP + derived STL + FCStd, same protocol as the pedal |
| Edit source, not generated artifacts (text-to-cad) | all arm geometry flows from module constants + program params; iteration only via `update_design_program`; failed rebuild keeps accepted revision (F04 transaction, inherited) |
| Snapshot validation mandatory (text-to-cad) | new `scripts/render_snapshot.py`: parse exported STL → matplotlib PNG in workspace, for the demo checklist (agent-loop multimodal review stays F16) |
| Repair loop: one error + one correction, smallest change (text-to-cad) | `strut_radius_mm` range floor **1.5** so the demo's scripted 0.8 mm failure hard-rejects at preflight with the valid range named; ranges chosen mutually geometric-safe so no cross-param check is needed yet; failure notes recorded for F13 |
| Report only checks that ran (text-to-cad ≈ solver honesty) | arm solve/fallback payloads state `method`, `mesh_max_size_mm`, `not_verified` — never a silent estimate |
| Validate-then-publish revisions, scoped surface, additive-first (vibecad) | inherited: program rev/hash transaction, `create_uav_arm` listed in `FREECAD_MUTATING_TOOLS` for HITL, no renames — the only existing-code touches are additive rows plus one test fixture swap |

## Geometry spec (fixed constants tuned in implementation; all mm)

- **Frame**: arm along X (root→tip), thrust/load along Z (transverse tip load → cantilever bending).
- **Root clamp boss**: block (~36×28×20) with two M3 clamp-bolt through-holes — clamps to the center plate; fixed BC faces.
- **Tapered arm**: box section tapering root (~24×12) → tip (~16×8), length = `arm_length_mm` (default 180, range 120–320); 1.5 mm solid skins top/bottom/sides; interior pocket = the lattice **design space** (mirrors the pedal's pocket discipline).
- **Tip motor-mount ring**: annulus (OD ~34 / ID ~26) with 4× M3 clearance holes on a fixed bolt circle.
- **Variants**: `solid` \| `xtruss` (reuses the pedal's lattice helper pattern; `fcc` intentionally excluded — additive later).
- **Defaults**: cell 15 (range 6–30), strut radius 2.0 (range 1.5–4.0), material `al6061t6`, mesh 4.0 mm, tip force 120 N (analysis param, not a program param).
- **Acceptance bands for tuning constants** (checked against the analytical estimate, not vibes): solid Al arm @120 N → SF ≈ 2.5–5, tip deflection 0.3–1.0 mm, mass 55–90 g; default xtruss variant stays SF ≥ 1.5 so the demo's edit story (fail at 0.8 strut, win at 12 mm cells) has room on both sides.

## Implementation steps

1. **New `companion/tools/uav_arm.py`** mirroring `brake_pedal.py`: constants, `WEB_TYPES`, `normalize_web_type`, `material_overrides`, pure-Python volume estimators, `memory_geometry`, `fallback_fea_result`, `_FREECAD_GEOM_HELPERS` + single `build_arm_body` shared by create/FEM scripts (fuse boss + skins + ring; lattice clipped to pocket; `isValid()` check), `UAVArmGenerator` demo class, `build_geometry_script` (F03 gate + STEP/STL/FCStd + `COMPANION_JSON` payload), `build_fem_script` (in-script BC pickers: clamp-boss bolt cylinders + boss root face fixed, ring face 120 N; node gate 20–25k; `FemToolsCcx` static; harvest von Mises + displacement + `max_vm_location_mm`).
2. **Add-a-row edits**: `design_program.py` (KNOWN_PARTS / PARAM_SPECS / WEB_TYPES / FIXED_CONSTANTS / default_params + `normalize_changes` uav branch), `materials.py` (DEFAULT_PART_MATERIAL), `estimate.py` (`uav_arm_expected_mpa` tapered-cantilever + dispatch), `cad_fea.py` (`create_uav_arm`, `_rebuild_from_program` + `apply_load_and_solve` dispatch branches, `_call_tool_raw`, TOOL_SPECS, precomputed/open-in-freecad candidates), `agent/tools.py` (Args model, tool entry, mutating list), `tools/__init__.py` re-export, `graph.py` router phrases (uav/arm/quadcopter/drone/motor mount).
3. **Live FreeCAD pass** (if `FreeCADCmd` discovered — proven on this machine per PLAN F27-note): tune constants against acceptance bands; generate goldens `data/results/uav_arm_{solid,xtruss}_precomputed.json` (portable content, no machine paths). If unavailable: skip goldens, evals ride fallback paths, note in ADR.
4. **Snapshot renderer**: `scripts/render_snapshot.py` (pure-Python STL parse → matplotlib Poly3DCollection PNG); graceful exit if matplotlib missing (add it to the venv only if needed).
5. **Tests**: new `tests/test_uav_arm.py` (FreeCAD-absent pattern: memory geometry, estimator, preflight ranges, program round-trip, fallback FEA, golden-untouched rule); swap the `uav_arm` "unknown part" fixture in `tests/test_design_program.py` (~line 210) to a genuinely unknown name; routing tests; `fakes.py` StubTools branch only if agent-loop evals need it.
6. **Evals**: `eval/cases.json` — create ok (fields incl. mass/volume), bad web_type → `bad_params`, program update (cell 12 on uav_arm), solve (expect_ok with honesty fields), agent case for the demo prompt.
7. **Docs**: `docs/tool_reference.md` row; `Features.md` section (Pitch · Script · Tests · Evals · Demo prompts · Interview Qs per AGENTS rule 4); `docs/uav_arm_lattice.md` design-vs-non-design map; **ADR-011** (param surface incl. `arm_length_mm`, solid|xtruss only, strut floor 1.5, goldens decision, snapshot script); mark PLAN.md F26 row done.

## Out of scope (deliberate)

F27 modal/frequency + 240 Hz decision loop (next session, own ADR) · `fcc` variant · surrogate/compare changes · F10 load-case params (force stays a tool arg) · any rename or contract change.

## Verification (AGENTS.md gates)

`.venv/bin/python -m pytest tests/ -q` → pass; `.venv/bin/python eval/run_eval.py` → pass; `scripts/smoke_freecad.py` + one live arm solve if FreeCAD present; grep goldens/scripts for machine-specific paths before commit.