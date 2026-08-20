> Internal — maintainer notes, not a user guide.

# Implementation Plan — Interactive CAD/FEA Visual Demo & AI Engineering Console

Revamp [`demo/demo_catalog.html`](demo/demo_catalog.html) into an aerospace-grade **Simulation Engineer Console & AI Architecture Visualizer**. It anchors the entire feature catalog (P0 through P2) around a real-world **UAV Arm Engineering Narrative**, providing 5 distinct prompts per feature, separated "What Should Happen" vs "Value" sections, and deep AI Engineering teardowns (Guardrails, Evals, Memory, Outcome Contracts).

---

## User Review Required

> [!IMPORTANT]
> **Anti-Slop Visual Theme Selection**:
> The dashboard will be built with a bespoke **"FEA Telemetry & Aerospace Workstation"** design system (dark titanium palette `#070b12`, CalculiX stress-contour accents, glassmorphic inspection cards, interactive timeline stepper, and interactive pipeline inspector). No generic templates or boilerplate styling.

> [!NOTE]
> **Scope of Coverage**:
> The dashboard will provide **5 distinct prompts per feature** across all implemented (F01, F02, F03, F04, F06, F07, F08, F09, F26) and near-term planned roadmap features (F27 Modal, F10 Configurable Loads, F12 Surrogate sweeps), totaling over 45+ comprehensive engineering prompts.

---

## Architecture & Visual System Design

### 1. The Aerospace CAD/FEA Narrative Arc (Top Story)
The catalog will open with an interactive **Mission Briefing: Designing a 180 mm Quadcopter UAV Arm**:
- **Act 1: Baseline Architecture & Mounting Constraints**: Clamping to center plate (root boss) + motor ring mounting under 120 N thrust.
- **Act 2: Generative Lightweighting**: Converting solid box core into an exposed X-truss lattice with solid load-bearing chord rails to achieve **~−17% mass reduction** (157 g $\rightarrow$ 130 g).
- **Act 3: Simulation Rigor & Verification**: Cross-checking 3D CalculiX FEA against closed-form analytical cantilever beam theory and running multi-density mesh convergence.
- **Act 4: High-Performance Material Optimization**: Evaluating Al 6061-T6 vs Al 7075-T6 vs Ti-6Al-4V under safety factor $\ge 1.5$.
- **Act 5: Vibration Dynamics (F27 Preview)**: Frequency studies to ensure first natural mode $f_1 > 240\text{ Hz}$ avoids motor/rotor resonance.

---

### 2. Multi-Layer Technical Architecture Diagram
An SVG/CSS visual flowchart mapping the full data lifecycle:
1. **Client / Transport Layer**: Browser UI, Server-Sent Events (`/api/chat/stream`), `thread_id` context binding.
2. **LangGraph Cognitive Engine**: `MemorySaver` checkpointing, state sync with FreeCAD session, heuristic router vs Gemini tool calling.
3. **Guardrails & Preflight Layer**: F03 B-Rep validity (`isValid()`), bounding box limits, non-positive parameter rejections, F07 analytical estimators.
4. **Headless Simulation Subsystem**: `FreeCADCmd` headless execution, process group isolation (`killpg`), Gmsh Delaunay mesher, CalculiX static FEA solver.
5. **Outcome & Persistence Layer**: F02 envelope (1 error + 1 concrete fix), F06 JSONL run history, spatial node tensor extraction $(X, Y, Z)$.

---

### 3. Feature Breakdown: 5 Prompts Per Feature (P0 to P2)

Every prompt card will have 4 distinct sections:
1. **The Prompt (with 1-click copy)**.
2. **What Should Happen** (exact tool calls, parameters, revision bumps, state mutations).
3. **Value & Demo Story** (why this matters to a mechanical engineer / hiring manager).
4. **AI Engineering Deep-Dive**:
   - **Cognitive Pattern**: Tool Calling / ReAct / Plan-and-Solve / Structured Extraction.
   - **Guardrails & Safety**: Preflight validation stage, B-Rep geometry gate, schema bounds.
   - **Memory & State**: LangGraph thread state, design program rev hash, session sync.
   - **Evals & Verification**: Associated unit test in `tests/`, eval case in `eval/cases.json`, solver honesty receipt.

#### Features Covered (5 Prompts Each):
- **F01 & RAG**: Material constants, analytical formulas, unit conversions, refusal of unverified alloys, multi-citation retrieval.
- **F02 & Outcome Envelope**: Unknown tool recovery, non-positive geometry rejection, malformed parameter handling, receipts inspection, raw traceback redaction.
- **F03 & B-Rep Validation Gate**: `isValid()` failure catch, self-intersecting lattice trap, bounding box overflow, negative dimensions, volume sanity check.
- **F04 & Design Program Layer**: Parametric baseline create, cell size update, strut radius edit, no-op idempotency check, out-of-range rollback.
- **F06 & Spatial Run History**: Latest solve query, 3D stress concentration coordinates $(X,Y,Z)$, multi-run comparison, run ID historical fetch, session audit list.
- **F07 & Analytical Pre-Flight**: Cantilever beam expected vs actual, divergence warning on coarse mesh, pedal bending estimate, UAV arm root bending, force scaling check.
- **F08 & Automated Mesh Convergence**: 3-density mesh study ($5.0 \rightarrow 3.5 \rightarrow 2.5\text{ mm}$), asymptotic convergence recommendation, FCC precomputed refusal, custom mesh density input, element count guard.
- **F09 & Material Selection**: Ti vs Al 7075 trade study, PA12 polymer deflection warning, unknown alloy reject, program material swap, density vs SF ranking.
- **F26 & Flagship UAV Arm**: Solid aluminum baseline solve, X-truss lattice lightweighting (~−17%, 157 g → 130 g), strut floor safety rejection (0.8 mm), arm length parameter sweep (120-320 mm), motor ring clearance hole verification.
- **F27 & Modal Dynamics (Preview)**: First natural frequency solve, mass vs frequency trade-off, rotor 240 Hz resonance check, mode shape extraction, stiffening rail parameter edit.

---

### 4. Interactive Experience Elements
- **Interactive Narrative Mode**: Click through the 5-step engineering story with visual 3D part anatomy diagrams.
- **AI Engineering Inspector Modal/Drawer**: Click any prompt to expand the deep AI Engineering teardown (inspect the JSON schema, test fixture, and LangGraph node sequence).
- **Search & Multi-Filter Bar**: Filter by Priority (P0/P1/P2), Part Family (UAV Arm, Brake Pedal, Cantilever), or AI Concept (Guardrails, Memory, Evals, RAG).
- **One-Click Clipboard Prompts**: Instant copy with visual feedback for demo execution.

---

## Proposed Changes

### Documentation & UI

#### [MODIFY] [demo/demo_catalog.html](demo/demo_catalog.html)
- Rebuild the entire file with:
  - Narrative story header (CAD & Simulation Engineer perspective).
  - High-resolution SVG architecture flowchart detailing the full LangGraph + FreeCAD lifecycle.
  - 5 comprehensive prompts per feature across all P0 to P2 features.
  - Clear separation between **What Should Happen** and **Value / Demo Story**.
  - Dedicated **AI Engineering Panels** (Guardrails, Evals, Memory, Cognitive Pattern) for every single prompt.
  - Bespoke dark telemetry styling with interactive filtering, search, and copy utilities.

---

## Verification Plan

### Manual Visual Verification (Zero Repo Bloat)
- **No automated test code will be created or added** to ensure the repository remains lean and uncluttered.
- Open [`demo/demo_catalog.html`](demo/demo_catalog.html) directly in your browser (`open demo/demo_catalog.html`).
- Visually verify:
  - The **Aerospace Simulation Engineer Story** reads clearly at the top.
  - The **Technical Architecture Flowchart** renders crisply with all 5 layers.
  - All **5 prompts per feature (P0 to P2)** have separated "What Should Happen", "Value", and "AI Engineering" breakdowns.
  - Interactive filter buttons, search, and one-click copy buttons work instantly.
