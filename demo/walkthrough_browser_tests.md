> Internal — maintainer notes, not a user guide.

# Walkthrough — Headed Browser UI Automation Suite (45 Tests)

All **45 automated Playwright browser tests** (36 single-shot prompt tests + 9 multi-turn continuous user journeys) have been implemented and verified with **100% pass rate** in a single visible Chromium window.

---

## 1. What Was Implemented

### Dedicated Browser Test Suite ([`tests/test_browser_ui.py`](tests/test_browser_ui.py))
- **45 Playwright test cases** targeting the FastAPI Web UI:
  - **Group 1 (F01 RAG)**: 4 tests for material properties, analytical formulas, and allowables.
  - **Group 2 (F02 Outcome Envelope)**: 4 tests for compact errors, unknown tool recovery, and negative dimension rejections.
  - **Group 3 (F03 B-Rep Guardrails)**: 4 tests for self-intersecting struts, degenerate volumes, and geometry validation.
  - **Group 4 (F04 Design Programs)**: 4 tests for parameter updates, idempotent revisions, and dry-run preview.
  - **Group 5 (F06 Spatial Run History)**: 4 tests for peak stress extraction, run listing, comparison, and hotspot coordinates.
  - **Group 6 (F07 Analytical Preflight)**: 4 tests for Euler-Bernoulli beam theory cross-checking and FEA divergence.
  - **Group 7 (F08 Mesh Convergence)**: 4 tests for multi-density sweeps, asymptotic delta checks, and displacement convergence.
  - **Group 8 (F09 Materials Engine)**: 4 tests for trade study matrices, polymer viscoelastic disclaimers, and material switches.
  - **Group 9 (F26 Flagship UAV Arm)**: 4 tests for solid baseline, X-truss lightweighting, 0.8 mm floor rejection, and length scaling.
  - **Continuous User Journeys (9 Multi-turn Tests)**:
    - `test_journey_uav_arm_lifecycle`: 4-turn full UAV arm engineering progression.
    - `test_journey_brake_pedal_optimization`: 3-turn brake pedal optimization.
    - `test_journey_mesh_convergence_study`: 3-turn Gmsh mesh sweep.
    - `test_journey_material_selection_and_rebuild`: 3-turn material trade study.
    - `test_journey_analytical_rigor`: 2-turn FEA vs analytical cross-check.
    - `test_journey_spatial_run_history`: 3-turn multi-run logging and coordinate extraction.
    - `test_journey_brep_guardrails`: 2-turn B-Rep geometry rejection & recovery.
    - `test_journey_outcome_envelope_recovery`: 2-turn error recovery.
    - `test_journey_rag_and_out_of_domain`: 2-turn domain boundary handling.

### Deterministic Test Infrastructure ([`tests/conftest.py`](tests/conftest.py) & [`tests/fakes.py`](tests/fakes.py))
- **`SmartDemoMockLLM`**: Deterministic mock model responding to all catalog prompts without incurring LLM token costs or hitting API rate limits.
- **Dynamic Port Server Fixture (`test_server_url`)**: Spins up the FastAPI application on an ephemeral port (`127.0.0.1:0`) in a background daemon thread.
- **Thread Context Safety**: Wrapped `_current_thread_id.reset` in `cad_thread_scope` with `ValueError` protection to support cross-context async generators in streaming responses.

---

## 2. Verification Results

### Automated Playwright Browser Tests
```bash
$ .venv/bin/python -m pytest tests/test_browser_ui.py -v
======================= 45 passed, 2 warnings in 13.83s ========================
```
- **45 passed in 13.83 seconds**
- Zero JavaScript uncaught exceptions (`pageerror`) across all 45 runs
- Zero UI hangs or timeout errors

### Full Repository Test Suite
```bash
$ .venv/bin/python -m pytest tests/ -q
........................................................................ [ 35%]
........................................................................ [ 71%]
.........................................................                [100%]
201 passed, 2 warnings in 22.38s
```
- **201 passed across all 11 test modules** (100% pass rate)

---

## 3. Demo Catalog & Presentation Assets

All presentation materials are organized in the [`demo/`](demo) folder:
- [`demo/demo_catalog.html`](demo/demo_catalog.html): Interactive Aerospace Simulation Console with 5-layer architecture diagram & 3-column AI teardowns.
- [`demo/DEMO_SCRIPT.md`](demo/DEMO_SCRIPT.md): Step-by-step interview presentation script.
- [`demo/Features.md`](demo/Features.md): Pitch, scripts, and interview Q&A for every feature.
- [`demo/PLAN_BROWSER_TESTS.md`](demo/PLAN_BROWSER_TESTS.md): Full browser test technical specification.
- [`demo/walkthrough.md`](demo/walkthrough.md): Aerospace Simulation Console walkthrough.
- [`demo/walkthrough_browser_tests.md`](demo/walkthrough_browser_tests.md): Browser UI automation test suite walkthrough.
