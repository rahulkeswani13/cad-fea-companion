> Internal — maintainer notes, not a user guide.

# Plan — Complete 36-Prompt Mocked Browser UI Test Suite

Comprehensive technical specification for implementing automated browser UI tests for all **36 demo prompts** across the CAD/FEA Companion.

**Scope**: 100% Mocked Browser Tests (Headed by default with visible Chromium window, fast execution in ~8 seconds, $0.00 API token cost, zero rate limits).

---

## 1. Overview & Architecture

The browser test suite uses **`pytest-playwright`** to launch a real visible Chromium browser window on your desktop. 

The browser interacts with the actual web frontend ([`companion/static/index.html`](companion/static/index.html)), typing prompts, clicking buttons, and evaluating the DOM. 
The backend runs in-process with **`ScriptedLLMProvider`** and **`StubTools`** from [`tests/fakes.py`](tests/fakes.py), delivering instant, deterministic responses without touching the Gemini API or launching external FreeCAD/Gmsh processes.

```
┌────────────────────────────────────────────────────────┐
│   Playwright Browser (Visible Headed Chromium Window)  │
│   - Types into #msg, clicks #send, clicks pills        │
│   - Verifies DOM elements, Markdown HTML, Tool Chips   │
│   - Listens for unhandled JS errors (pageerror)        │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP & SSE (/api/chat/stream)
                            ▼
┌────────────────────────────────────────────────────────┐
│   FastAPI In-Process Server (tests/conftest.py)        │
│   - Dynamic port fixture (http://127.0.0.1:0)          │
│   - Mock MemorySaver thread checkpointing              │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│   Mock Test Doubles (tests/fakes.py)                   │
│   - ScriptedLLMProvider: Instant deterministic turns   │
│   - StubTools: In-memory CAD volumes & FEA formulas    │
└────────────────────────────────────────────────────────┘
```

---

## 2. Universal Pass & Failure Conditions

### Global Pass Conditions:
1. **Response Rendered**: A new `.msg.assistant` card appears inside `#log`.
2. **Markdown Parsed**: Text is parsed into semantic HTML (`<p>`, `<code>`, `<strong>`, `<table>`, `<ul>`), never raw `**markdown**` text.
3. **No UI Hangs**: The `#send` button re-enables and the `#msg` input textarea clears.
4. **Zero Console Crashes**: `page.on("pageerror")` captures 0 uncaught JavaScript runtime exceptions.

### Global Failure Conditions:
1. **Timeout (> 5s)**: Any hanging SSE stream or frozen event listener.
2. **Raw Traceback Leak**: Any Python traceback string (`Traceback (most recent call last)`) rendered into the UI.
3. **Broken Input State**: `#send` button remains disabled, preventing subsequent turns.
4. **JavaScript Crash**: Any frontend `TypeError` or `DOMPurify` sanitizer error.

---

## 3. Complete Catalog of All 36 Mocked Browser Tests

---

### Group 1: F01 — Grounded RAG & Material Property Retrieval (4 Prompts)

#### 1. `test_ui_f01_al6061_properties`
* **Prompt**: `"What is the yield strength and density of Al 6061-T6?"`
* **How it Passes**: Assistant response renders 276 MPa yield strength and 2.70 g/cm³ density, citing `[docs/materials.md]`.
* **How it Fails**: Hallucinated numbers, missing citation tag, or unparsed markdown.

#### 2. `test_ui_f01_cantilever_analytical_formula`
* **Prompt**: `"What is the analytical bending stress formula for a rectangular cantilever beam?"`
* **How it Passes**: Renders the closed-form equation $\sigma = \frac{6FL}{bh^2}$ or `(6*F*L)/(b*h^2)` formatted with citation.
* **How it Fails**: Missing equation variables or broken citation formatting.

#### 3. `test_ui_f01_structural_steel_modulus`
* **Prompt**: `"What Young's modulus should I assume for structural steel in this demo?"`
* **How it Passes**: Assistant returns 210 GPa with citation `[docs/materials.md]`.
* **How it Fails**: Returns incorrect units (e.g. MPa instead of GPa) or fails to cite source.

#### 4. `test_ui_f01_ti6al4v_allowables`
* **Prompt**: `"What are the allowable stress limits for Titanium Ti-6Al-4V?"`
* **How it Passes**: Renders yield strength (~880 MPa) and ultimate strength (~950 MPa) with citation.
* **How it Fails**: Missing document citation or raw markdown formatting leaks.

---

### Group 2: F02 — Outcome Envelope & Error Recovery (4 Prompts)

#### 5. `test_ui_f02_solve_without_geometry`
* **Prompt**: `"Run an FEA solve without creating any geometry first."`
* **How it Passes**: Assistant renders clean F02 error card: "No active geometry. Call create_brake_pedal or create_cantilever first." `#send` is immediately re-enabled.
* **How it Fails**: Raw Python `KeyError`/`AttributeError` traceback is shown, or UI freezes.

#### 6. `test_ui_f02_unknown_tool_recovery`
* **Prompt**: `"Execute tool nonexistent_cad_generator."`
* **How it Passes**: Renders safe error: "Unknown tool 'nonexistent_cad_generator'. Available tools: create_brake_pedal, create_uav_arm...".
* **How it Fails**: Backend crashes with unhandled 500 error or blank UI response.

#### 7. `test_ui_f02_cantilever_negative_length`
* **Prompt**: `"Create a cantilever beam with length -50 mm."`
* **How it Passes**: Renders error class `bad_params` explaining dimensions must be strictly positive.
* **How it Fails**: System attempts to construct negative geometry or throws unhandled exception.

#### 8. `test_ui_f02_pedal_negative_cell_size`
* **Prompt**: `"Create a brake pedal with cell size -5 mm."`
* **How it Passes**: Renders error notification with suggested valid range `[5.0, 40.0] mm`.
* **How it Fails**: Unhandled server error or raw exception trace.

---

### Group 3: F03 — B-Rep Geometry Validation Gate (4 Prompts)

#### 9. `test_ui_f03_self_intersecting_lattice_rejection`
* **Prompt**: `"Create a brake pedal with strut radius 8 mm and cell size 6 mm."`
* **How it Passes**: Renders pre-mesh B-Rep rejection notice: strut radius cannot exceed cell radius (self-intersecting solid).
* **How it Fails**: Subprocess hangs trying to mesh overlapping solids or crashes without explanation.

#### 10. `test_ui_f03_zero_height_cantilever`
* **Prompt**: `"Create a cantilever beam with height 0 mm."`
* **How it Passes**: Rejects with B-Rep invalidity warning (zero-volume degenerated solid).
* **How it Fails**: FreeCAD returns unhandled OpenCASCADE kernel crash.

#### 11. `test_ui_f03_invalid_web_type`
* **Prompt**: `"Create a brake pedal with invalid web type voronoi."`
* **How it Passes**: Rejects `voronoi` and lists accepted types: `solid`, `xtruss`, `fcc`.
* **How it Fails**: System attempts to evaluate undefined web type or crashes.

#### 12. `test_ui_f03_explicit_validate_geometry`
* **Prompt**: `"Validate the current CAD geometry."`
* **How it Passes**: Calls `validate_cad_geometry` and displays B-Rep validity status, bounding box limits, and watertight shell check.
* **How it Fails**: Tool fails to report geometric attributes or returns blank card.

---

### Group 4: F04 — Design Program Layer & Revision Hashing (4 Prompts)

#### 13. `test_ui_f04_baseline_pedal_init`
* **Prompt**: `"Create an X-truss brake pedal with 15 mm cells and solve 500 N."`
* **How it Passes**: Renders `create_brake_pedal` and `apply_load_and_solve` tool chips, rev 1 committed, 500 N solve metrics displayed.
* **How it Fails**: Program JSON is not created or tool chips are missing.

#### 14. `test_ui_f04_parameter_update_and_rebuild`
* **Prompt**: `"Update the brake pedal cell size to 12 mm and re-solve."`
* **How it Passes**: Confirms parameter hash change, bumps to rev 2, and displays updated solve metrics.
* **How it Fails**: Session resets to default instead of updating existing part.

#### 15. `test_ui_f04_noop_idempotency`
* **Prompt**: `"Set the brake pedal cell size to 12 mm again."`
* **How it Passes**: Detects identical parameter hash, returns `changed: false`, and notes CAD rebuild was skipped.
* **How it Fails**: Redundantly rebuilds CAD geometry or bumps revision unnecessarily.

#### 16. `test_ui_f04_dry_run_preview`
* **Prompt**: `"Preview changing strut radius to 3.5 mm without applying."`
* **How it Passes**: Outputs dry-run validation result and proposed hash without incrementing active disk revision.
* **How it Fails**: Overwrites active program file despite dry-run flag.

---

### Group 5: F06 — Spatial Run History & Auditing (4 Prompts)

#### 17. `test_ui_f06_latest_solve_spatial_stress`
* **Prompt**: `"What was the peak stress in the latest solve and where is it located?"`
* **How it Passes**: Displays peak von Mises stress (MPa) and exact 3D spatial node coordinates $(X, Y, Z)$ in mm.
* **How it Fails**: Missing spatial coordinates or missing solve record.

#### 18. `test_ui_f06_list_session_runs`
* **Prompt**: `"List all simulation runs in this session."`
* **How it Passes**: Renders a formatted audit table of past solve runs with Run IDs, timestamps, mesh sizes, and peak stresses.
* **How it Fails**: History table is empty or fails HTML table formatting.

#### 19. `test_ui_f06_compare_two_runs`
* **Prompt**: `"Compare run 1 and run 2."`
* **How it Passes**: Renders side-by-side comparison of mass, stress, and parameter diffs between rev 1 and rev 2.
* **How it Fails**: Fails to fetch prior run IDs or outputs unformatted text.

#### 20. `test_ui_f06_hotspot_coordinates`
* **Prompt**: `"Show me the coordinate of the maximum von Mises stress on the brake pedal."`
* **How it Passes**: Identifies pivot boss fillet region with $(X, Y, Z)$ coordinates.
* **How it Fails**: Omits coordinates or returns non-numeric values.

---

### Group 6: F07 — Pure-Python Analytical Closed-Form Estimators (4 Prompts)

#### 21. `test_ui_f07_cantilever_solve_and_analytical`
* **Prompt**: `"Create a cantilever beam 100x20x5 mm and solve under 100 N."`
* **How it Passes**: Displays FEA max von Mises (120 MPa) alongside `analytical_reference_mpa: 120.0`.
* **How it Fails**: Analytical reference is omitted or diverges significantly from 120 MPa.

#### 22. `test_ui_f07_expected_bending_stress_query`
* **Prompt**: `"What is the expected analytical bending stress for this cantilever?"`
* **How it Passes**: Returns exact closed-form calculation: $(6 \cdot 100 \cdot 100) / (20 \cdot 5^2) = 120\text{ MPa}$.
* **How it Fails**: Math error or missing unit formatting.

#### 23. `test_ui_f07_pedal_analytical_estimate`
* **Prompt**: `"What is the analytical stress estimate for a brake pedal under 500 N?"`
* **How it Passes**: Computes simplified cantilever beam bending estimate across pedal arm cross-section.
* **How it Fails**: Fails to compute estimate or claims analytical is impossible.

#### 24. `test_ui_f07_fea_vs_analytical_divergence_check`
* **Prompt**: `"How does the 3D FEA stress compare to the beam theory estimate?"`
* **How it Passes**: Reports delta percentage between CalculiX 3D tetrahedral FEA and 1D Euler-Bernoulli beam theory.
* **How it Fails**: Fails to compare the two fields or hallucinates numbers.

---

### Group 7: F08 — Automated Mesh Convergence Study (4 Prompts)

#### 25. `test_ui_f08_pedal_mesh_convergence_study`
* **Prompt**: `"Run a mesh convergence study on the brake pedal."`
* **How it Passes**: Renders 3-density mesh table (5.0 mm, 3.5 mm, 2.5 mm), stress delta curve, and recommended mesh size.
* **How it Fails**: Table is missing or convergence recommendation is omitted.

#### 26. `test_ui_f08_fcc_convergence_refusal`
* **Prompt**: `"Run a mesh convergence study on an FCC lattice pedal."`
* **How it Passes**: Refuses with domain explanation: FCC uses precomputed demo KPIs, live solves required for mesh studies.
* **How it Fails**: Generates fake convergence curve on static seed data.

#### 27. `test_ui_f08_custom_mesh_sizes_study`
* **Prompt**: `"Run convergence on the cantilever at mesh sizes 4.0, 2.5, and 1.5 mm."`
* **How it Passes**: Passes custom array `[4.0, 2.5, 1.5]` to tool, outputs 3-step convergence table.
* **How it Fails**: Ignores custom array and defaults to standard sizes.

#### 28. `test_ui_f08_deflection_mesh_sensitivity`
* **Prompt**: `"How does tip deflection change between the coarse and fine meshes?"`
* **How it Passes**: Compares max displacement across mesh ladder (e.g. 1.62 mm &rarr; 1.69 mm).
* **How it Fails**: Deflection field is missing from report.

---

### Group 8: F09 — Material Parameterization & Trade Studies (4 Prompts)

#### 29. `test_ui_f09_ti_vs_al7075_trade_study`
* **Prompt**: `"Compare making the brake pedal from Titanium vs Aluminum 7075-T6."`
* **How it Passes**: Renders trade study table (Mass, Stress, SF), recommends Al 7075-T6 (0.25 kg vs 0.40 kg Ti).
* **How it Fails**: Table missing or recommendation ignores mass optimization.

#### 30. `test_ui_f09_pa12_polymer_disclaimer`
* **Prompt**: `"What happens if we switch the brake pedal material to PA12 Nylon?"`
* **How it Passes**: Reports 0.09 kg mass but attaches explicit `NOT VERIFIED` disclaimer for polymer deflection.
* **How it Fails**: Omits non-linear polymer disclaimer.

#### 31. `test_ui_f09_unknown_alloy_rejection`
* **Prompt**: `"Change the brake pedal material to Vibranium-X."`
* **How it Passes**: Rejects invalid alloy and lists supported materials (Al 6061-T6, Al 7075-T6, Ti-6Al-4V, PA12, Steel).
* **How it Fails**: Accepts fake material or crashes backend.

#### 32. `test_ui_f09_material_program_rebuild`
* **Prompt**: `"Set the pedal material to 7075 aluminum and rebuild."`
* **How it Passes**: Updates program `material: "al7075t6"`, bumps revision hash, and binds updated yield strength (503 MPa).
* **How it Fails**: Fails to update program file or ignores alias '7075'.

---

### Group 9: F26 — Flagship Parametric UAV Arm (4 Prompts)

#### 33. `test_ui_f26_solid_uav_arm_120n_solve`
* **Prompt**: `"Create a solid aluminum UAV arm and solve it under a 120 N tip thrust."`
* **How it Passes**: Renders `create_uav_arm` and `apply_load_and_solve` chips, 157 g mass, SF 6.2, and STEP/STL links.
* **How it Fails**: Tool chips missing or geometry values unrendered.

#### 34. `test_ui_f26_uav_arm_generative_xtruss`
* **Prompt**: `"Change the UAV arm to an X-truss lattice with 12 mm cells and 1.8 mm struts and solve."`
* **How it Passes**: Replaces solid core with X-truss lattice while keeping solid chord rails, confirms ~17% mass reduction (130 g).
* **How it Fails**: Mass reduction not reported or chord rails missing.

#### 35. `test_ui_f26_strut_radius_floor_rejection`
* **Prompt**: `"Set UAV arm strut radius to 0.8 mm."`
* **How it Passes**: Hard rejects at preflight (0.8 mm < 1.5 mm meshable floor), keeps valid revision on disk intact.
* **How it Fails**: Attempted rebuild crashes mesher or corrupts active revision.

#### 36. `test_ui_f26_arm_length_scaling`
* **Prompt**: `"Make the UAV arm 220 mm long and check new mass and stress."`
* **How it Passes**: Updates `arm_length_mm: 220`, regenerates lattice along length, reports increased root bending moment.
* **How it Fails**: Geometry length unchanged or solve fails to re-run.

---

---

## 4. Multi-Turn Feature Journey Tests (9 Continuous Sessions)

In addition to the 36 isolated tests, the suite includes **9 multi-turn continuous user journeys** ($36 + 9 = 45$ total tests). Each journey simulates a real human engineer having an uninterrupted 4-turn chat conversation in a single browser session, thoroughly validating multi-turn LangGraph thread memory.

---

#### J1. `test_journey_uav_arm_lifecycle`
* **Turn 1**: `"Create a solid aluminum UAV arm and solve it under a 120 N tip thrust."` &rarr; Verifies baseline CAD & FEA (rev 1, 157 g, SF 6.2).
* **Turn 2**: `"Change the UAV arm to an X-truss lattice with 12 mm cells and 1.8 mm struts and solve."` &rarr; Verifies ~17% mass reduction (rev 2, 130 g, solid chord rails intact).
* **Turn 3**: `"Set UAV arm strut radius to 0.8 mm."` &rarr; Verifies safe preflight rejection, rev 2 preserved.
* **Turn 4**: `"Make the UAV arm 220 mm long and check new mass and stress."` &rarr; Verifies parametric length scaling (rev 3; no committed golden at 220 mm).

---

#### J2. `test_journey_brake_pedal_optimization`
* **Turn 1**: `"Create an X-truss brake pedal with 15 mm cells and solve 500 N."` &rarr; Verifies rev 1 initialization and solve.
* **Turn 2**: `"Update the brake pedal cell size to 12 mm and re-solve."` &rarr; Verifies rev 2 parameter mutation.
* **Turn 3**: `"Set the brake pedal cell size to 12 mm again."` &rarr; Verifies no-op detection (`changed: false`, keeps rev 2).
* **Turn 4**: `"Preview changing strut radius to 3.5 mm without applying."` &rarr; Verifies dry-run preview.

---

#### J3. `test_journey_mesh_convergence_study`
* **Turn 1**: `"Create a cantilever beam 100x20x5 mm and solve under 100 N."` &rarr; Verifies initial solve.
* **Turn 2**: `"Run convergence on the cantilever at mesh sizes 4.0, 2.5, and 1.5 mm."` &rarr; Verifies custom 3-step convergence table.
* **Turn 3**: `"How does tip deflection change between the coarse and fine meshes?"` &rarr; Verifies multi-field tracking.
* **Turn 4**: `"Run a mesh convergence study on an FCC lattice pedal."` &rarr; Verifies domain-specific refusal.

---

#### J4. `test_journey_material_selection_and_rebuild`
* **Turn 1**: `"Create an X-truss brake pedal with 15 mm cells and solve 500 N."` &rarr; Verifies baseline solve.
* **Turn 2**: `"Compare making the brake pedal from Titanium vs Aluminum 7075-T6."` &rarr; Verifies trade study table & Al 7075 recommendation.
* **Turn 3**: `"What happens if we switch the brake pedal material to PA12 Nylon?"` &rarr; Verifies 0.09 kg mass with `NOT VERIFIED` deflection disclaimer.
* **Turn 4**: `"Set the pedal material to 7075 aluminum and rebuild."` &rarr; Verifies program update & rev 2 rebuild.

---

#### J5. `test_journey_analytical_rigor`
* **Turn 1**: `"Create a cantilever beam 100x20x5 mm and solve under 100 N."` &rarr; Verifies 120 MPa solve.
* **Turn 2**: `"What is the analytical bending stress formula for a rectangular cantilever beam?"` &rarr; Verifies RAG formula response with citation.
* **Turn 3**: `"How does the 3D FEA stress compare to the beam theory estimate?"` &rarr; Verifies 0.0% divergence check.
* **Turn 4**: `"What is the analytical stress estimate for a brake pedal under 500 N?"` &rarr; Verifies simplified beam calculation.

---

#### J6. `test_journey_spatial_run_history`
* **Turn 1**: `"Create a cantilever beam 100x20x5 mm and solve under 100 N."` &rarr; Verifies Run 1 logged in history.
* **Turn 2**: `"Create a solid aluminum UAV arm and solve it under a 120 N tip thrust."` &rarr; Verifies Run 2 logged in history.
* **Turn 3**: `"List all simulation runs in this session."` &rarr; Verifies multi-run audit table.
* **Turn 4**: `"What was the peak stress in the latest solve and where is it located?"` &rarr; Verifies $(X, Y, Z)$ spatial coordinate extraction.

---

#### J7. `test_journey_brep_guardrails`
* **Turn 1**: `"Create a brake pedal with invalid web type voronoi."` &rarr; Verifies rejection.
* **Turn 2**: `"Create a brake pedal with strut radius 8 mm and cell size 6 mm."` &rarr; Verifies self-intersecting lattice rejection.
* **Turn 3**: `"Create an X-truss brake pedal with 15 mm cells and solve 500 N."` &rarr; Verifies recovery to valid part.
* **Turn 4**: `"Validate the current CAD geometry."` &rarr; Verifies watertight B-Rep confirmation.

---

#### J8. `test_journey_outcome_envelope_recovery`
* **Turn 1**: `"Run an FEA solve without creating any geometry first."` &rarr; Verifies clean "no geometry" F02 error card.
* **Turn 2**: `"Execute tool nonexistent_cad_generator."` &rarr; Verifies available tools suggestion.
* **Turn 3**: `"Create a cantilever beam with length -50 mm."` &rarr; Verifies positive dimension requirement.
* **Turn 4**: `"Create a cantilever beam 100x20x5 mm and solve under 100 N."` &rarr; Verifies successful recovery.

---

#### J9. `test_journey_rag_and_out_of_domain`
* **Turn 1**: `"What is the yield strength and density of Al 6061-T6?"` &rarr; Verifies grounded properties + citation.
* **Turn 2**: `"What are the allowable stress limits for Titanium Ti-6Al-4V?"` &rarr; Verifies allowable stress + citation.
* **Turn 3**: `"What Young's modulus should I assume for structural steel in this demo?"` &rarr; Verifies 210 GPa + citation.
* **Turn 4**: `"What is the weather in Tokyo?"` &rarr; Verifies 0 tools called and polite out-of-domain refusal.

---

## 5. Execution Environment & Test Fixtures

1. **Single Visible Browser Window (Desktop Playback)**:
   - Uses a session-scoped visible Chromium browser fixture. All tests run in sequence inside the same window, providing a clean, fluid desktop viewing experience.
2. **HITL Confirmation Automation**:
   - When the HITL modal appears, the bot pauses for **500 ms** (allowing you to clearly see the dialog on screen), then clicks **"Confirm / Approve"** to resume.
3. **Failure Screenshot Capture**:
   - If any assertion fails, Playwright automatically saves a timestamped screenshot of the full browser DOM to `demo/test_failures/`.

---

## 6. Implementation Files

1. **[`requirements.txt`](requirements.txt)**: Add `pytest-playwright>=0.5.0`.
2. **[`tests/conftest.py`](tests/conftest.py)**:
   - Dynamic port FastAPI server fixture (`http://127.0.0.1:0`).
   - Single visible Chromium browser fixture with `headless=False`, `slow_mo=200`, and failure screenshot hooks.
3. **[`tests/fakes.py`](tests/fakes.py)**: Ensure all 9 tool branches and `create_uav_arm` exist in `StubTools`.
4. **[`tests/test_browser_ui.py`](tests/test_browser_ui.py)**: Implement all 36 single-shot tests + 9 multi-turn journey tests (45 total).

---

## 7. Verification Commands

```bash
# 1. Install browser automation dependencies
.venv/bin/pip install pytest-playwright
.venv/bin/playwright install chromium

# 2. Run all 45 visible mocked browser tests (watch bot type on screen in ~15s)
.venv/bin/python -m pytest tests/test_browser_ui.py -v

# 3. Verify zero regressions on entire backend test suite (156 tests pass)
.venv/bin/python -m pytest tests/ -q
```

