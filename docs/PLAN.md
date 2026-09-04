# cad-fea-companion Development Plan (P0–P2, v2)

> Status: living roadmap — P0 done, P1 in progress.

Consolidated from: vibecad + text-to-cad repo studies, commercial simulation-assistant
feature research, the verified study doc, and the flagship-part research (FreeCAD
`femexamples`, microgen).

Companion documents: `demo/DEMO_SCRIPT.md` (30-min demo performance script),
`docs/adr/` (decision records), `AGENTS.md` (contribution policy).

## Strategy

Deepen the USP — **natural language in → physics-solved design decision out** — by borrowing
agent-architecture patterns from vibecad/text-to-cad, reaching chat-driven
simulation-assistant parity where cheap, and
adding two flagship parts so the demo shows real mechanical drama (not just the tutorial
brake pedal): a **UAV arm** (strut lattice + modal analysis) and a **lattice heat sink**
(gyroid TPMS + thermal analysis).

## Scope decisions (see ADR-001)

- Brake pedal stays as the onboarding/eval part; flagship parts carry the demo.
- No forking vibecad; no fluids track; additive-first changes only.
- Simulation breadth is proven: FreeCAD ships 74 headless-runnable FEM examples
  (`src/Mod/Fem/femexamples/` — frequency, buckling, thermomech, contact, centrifugal).
  Crib from these; do not invent solver plumbing.
- Lattice breadth: microgen (github.com/3MAH/microgen) for TPMS gyroid; the existing
  parametric strut approach remains the FEA-safe path (TPMS volume-meshing is the risk).

## Capability keys (R1–R7)

R1 agentic AI / LLM+ML deployment · R2 prompt-driven simulation execution ·
R3 prototypes & PoCs · R4 quality tooling · R5 metrics & optimization ·
R6 root-cause analysis · R7 Python/C++.

Effort unit: one focused session ≈ 2–4 h (learning curve priced in).

## P0 — Foundation + cheap chat-driven simulation-assistant parity (do first, in order)

| ID | Feature | Effort | Keys | Deps | Done when |
|----|---------|--------|-----|------|-----------|
| F01 | `AGENTS.md` + `docs/adr/` journal | 0.5 | R4 | — | Files merged; ADR-001 records scope |
| F02 | Tool outcome contract: `companion/tools/outcome.py`, compact success/failure envelopes, one error + one concrete correction, receipts (what changed, units, KPIs, elapsed) — **done 2026-08-16 (ADR-002)** | 1–2 | R4,R6 | — | Every tool returns through the envelope; no raw tracebacks in LLM context; tests cover both shapes |
| F03 | Pre-mesh B-Rep validation gate (`isValid()`, volume/bbox sanity, named failure stage) — **done 2026-08-16 (ADR-003)** | 1 | R4,R6 | F02 | Invalid geometry fails fast with actionable message before Gmsh; eval case added |
| F04 | Design program layer: persisted params + revision hash per part (`data/workspace/<part>_program.json`); `get_design_program` / `update_design_program`; range preflight; failed rebuild preserves accepted revision; no-op → `current` — **done 2026-08-16 (ADR-004)** | 3–4 | R1,R2,R3 | F02 | "set cell size to 12" edits + rebuilds without recreate; failure keeps prior state; tests + evals |
| F05 | Frozen workbench: active-domain in graph state; per-turn tool filtering (authoring vs analysis); frozen surface in trace — **skipped 2026-08-16 (ADR-005); revisit before F17** | 1–2 | R1 | — | Solve/compare not offered before geometry; heuristic router respects scoping |
| F06 | Rich result querying: per-run history (mass, max VM + location, deflections, reactions, mesh, method flag); `query_results` tool — **done 2026-08-16 (ADR-006)**; reactions deferred to F10, VM location captured on brake pedal | 1–2 | R2 | F02 | "where is stress concentrated" answered from stored results |
| F07 | Pre-flight analytical estimate before every solve; expected-vs-actual with divergence flag — **done 2026-08-16 (ADR-007)** | 1 | R2,R3 | F04 | Every solve shows expected range; large divergence flagged |
| F08 | Mesh convergence automation: `run_convergence_study` (2–3 densities, recommendation) — **done 2026-08-16 (ADR-009)** | 2 | R3,R6 | F02 | Report + recommended mesh size; docs always state mesh size |

## P1 — Differentiators + flagship part 1 (order as listed)

| ID | Feature | Effort | Keys | Deps | Done when |
|----|---------|--------|------|------|-----------|
| F09 | Material as parameter + selection guidance (6061-T6, 7075-T6, Ti-6Al-4V, PA12; multi-material compare; RAG-grounded) — **done 2026-08-16 (ADR-010; cited table in `data/materials.json` + `docs/materials.md`, `compare_materials` scaling, `material` program param)** | 2 | R2,R3 | F04 | "compare Ti vs Al" end-to-end with citations |
| F10 | Chat-configurable load cases (direction, magnitude, BC location as validated program params) | 2–3 | R1,R2 | F04 | "solve 700 N at 30° off-axis" produces correct setup |
| F11 | Async operation handles (`operation-N` registry, `read_operation`, subphase progress, UI polling) | 2–3 | R4 | F04 | Long solves stop blocking; cancellable |
| **F26** | **Flagship 1 — UAV arm part family**: parametric quadcopter arm (root clamp boss, tapered arm, tip motor-mount ring), strut-lattice web as design space; follows `brake_pedal.py` generator pattern — **done 2026-08-17 (ADR-011; solid + xtruss with chord rails, create_uav_arm, goldens at 120 N, mesh guidance per variant)** | 3–4 | R3 | F04 | create_uav_arm with solid/lattice variants, STEP export, metrics |
| **F29** | **React operator console at `/app`**: Vite+React+TS+Tailwind build in `web/`, committed to `companion/static/app/`; prompt library (`data/prompts.json` + `/api/prompts`) with dropdown + ⌘K palette; feature walkthroughs; state rail (design program / run history / solver status); FEA report cards; legacy console untouched — **done 2026-09-02 (ADR-015; plan in `docs/plans/console_ui_plan.md`)** | 3 | R4 | F02,F04,F06 | `/app` serves the console; additive GET endpoints unit-tested + eval'd; 45 legacy browser checks stay green |
| **F27** | Modal analysis in solve pipeline: frequency studies (reference: `femexamples` `boxanalysis_frequency`, `frequency_beamsimple`); first-N modes stored as results; "mass vs first natural frequency" joins compare/decision loop | 2–3 | R3 | F26 | "lightest arm with SF≥1.5 AND first mode above rotor excitation" answerable |
| F27-note | Measured on FreeCADCmd headless (2026-08-15): `frequency_beamsimple` — setup 0.3 s, CalculiX solve 5.2 s for 10 eigenmodes, FEA f1 12.661 Hz vs analytical 12.68 Hz (0.15%). API gotcha: `ccxtools.py` defines `CcxTools` twice; use `FemToolsCcx(analysis=…, solver=…)` (the last `CcxTools(solver)` subclass delegates analysis discovery). Probe-script pattern belongs in `scripts/` when F27 lands. | | | | |
| F12 | ML surrogate + design-space chat: sweep script → dataset (cell × strut × force → max VM, mass, deflection, first freq); small model (gradient boosting or tiny NN); instant what-if + maps; predictions labeled `estimate`; precomputed JSON is seed data | 4–6 | R1,R3,R5 | F04,F11,F27 | "map SF vs strut radius" answers in seconds with accuracy stats |
| F13 | Repair loop: failure-class table, cause + one correction per class, `docs/repair_loop.md` in corpus | 1–2 | R6 | F02 | Known failures return actionable hints; eval-tested |
| F14 | Skill-style docs restructure: trigger-based progressive references (briefs, tool_reference, validation, repair_loop) | 2–3 | R1 | — | Agent loads one small reference per task; retrieval precision improves |
| F15 | Embedding RAG + retrieval evals (local embeddings; TF-IDF fallback; recall@k before/after) | 2–3 | R1,R5 | F14 | Eval reports gains; no-key mode still works |
| F16 | Post-solve visual snapshot review: matplotlib render of stress/deformed shape/mode shape → Gemini multimodal sanity check before final answers | 2–3 | R3,R5 | F06,F11 | Agent "looks at" the plot; anomalies flagged |

## P2 — Stretch / integration (opportunistic)

| ID | Feature | Effort | Keys | Deps |
|----|---------|--------|------|------|
| F17 | Freeform workbench: `create_freeform` — agent-authored FreeCAD Python via `run_freecad_python`, validation gate, FreeCAD-API corpus | 3–5 | R1,R3 | F03,F05,F14 |
| **F28** | **Flagship 2 — heat sink + gyroid TPMS + thermal**: microgen gyroid fill in cold-plate envelope; steady conduction study (reference: `thermomech` examples); fallback = strut lattice if TPMS volume-meshing fails | 4–6 | R3 | F12,F27 |
| F18 | MCP server mode (FastMCP shim, localhost + token, serialized mutations) | 2–3 | R1 | F02,F04 |
| F19 | Provider abstraction (BaseProvider, budgets; Gemini + local Ollama) | 2–3 | R1 | F02 |
| F20 | text-to-cad composition demo (t2c CLI geometry → companion FEA loop) | 2 | R3 | F17 |
| F21 | vibecad-as-backend MCP experiment (prototype branch + ADR) | 2–3 | R1 | F18 |
| F22 | Skill packaging of the FEA loop (SKILL.md + thin CLIs) | 2–3 | R1,R3 | F14,F18 |
| F23 | GUI edit absorption, Route B only (drift detection, `import_edited_document`, "diverged from source") | 3–4 | R3 | F04 |
| F24 | Buckling study (reference: `ccx_buckling_flexuralbuckling`); solid vs lattice thin-structure comparison | 3–4 | R3 | F08 |
| F25 | C++ geometry worker (fluids-track signal only; never displaces P0/P1) | 5+ | R7 | — |

## Cross-cutting rules (every feature)

1. Unit tests in `tests/` + eval cases in `eval/cases.json` + ADR entry for decisions.
2. All tool results flow through the F02 envelope — no raw tracebacks or 90-field payloads in LLM context.
3. Solver answers always state: method (calculix / surrogate / analytical), mesh size, and what was **not** verified.
4. Additive-first; no breaking API renames without an ADR (mirrors vibecad policy).
5. CI (GitHub Actions: pytest + eval runner) added immediately after F02.

## Execution order

1. F01 (this repo: AGENTS.md, ADR-001, this plan).
2. F02 → F03 → F04 → ~~F05~~ (skipped, ADR-005) → F06 → F07 → F08 (P0 spine; F02/F03 first so later tools inherit the contract).
3. P1 in listed order — note F26/F27 (UAV arm + modal) land **before** F12 so surrogate sweeps include modal data.
4. P2 opportunistic; F28 (heat sink) after the surrogate/analysis plumbing exists.

## Explicitly out of scope

Forking vibecad · rebuilding native operation schemas · Route A GUI embedding (persistent
FreeCAD GUI process) · fluids track (C++/CFD/LBM) · assemblies, motion, image-to-mesh, drafting.
