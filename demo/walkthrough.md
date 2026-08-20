> Internal — maintainer notes, not a user guide.

# Walkthrough — Aerospace Simulation Engineer Console & AI Architecture Catalog

We revamped [`demo/demo_catalog.html`](demo/demo_catalog.html) into an interactive **Aerospace CAD/Simulation Engineering Workstation & AI Architecture Console**.

---

## Key Highlights of the Console

### 1. Aerospace Engineering Narrative (Mission Briefing)
A 5-phase engineering story at the top framing the entire demo around a **180 mm Quadcopter UAV Arm**:
- **Phase 01: Boundary Constraints**: Rigid root clamp boss & tip motor ring interface.
- **Phase 02: Topology & Lightweighting**: Converting solid core into an X-truss lattice with 1.5 mm solid chord rails to achieve **~−17% mass reduction** (157 g → 130 g).
- **Phase 03: Simulation Honesty**: Validating 3D CalculiX FEA against closed-form analytical cantilever beam equations.
- **Phase 04: Mesh Convergence**: Multi-density Gmsh sweeps (5.0 mm → 3.5 mm → 2.5 mm) ensuring asymptotic stress convergence.
- **Phase 05: Material Trade Study**: Evaluating Al 6061-T6 vs Al 7075-T6 vs Ti-6Al-4V under SF ≥ 1.5.

---

## 2. Multi-Layer Technical Architecture Diagram
High-resolution interactive SVG vector diagram illustrating all 5 system layers:
1. **Client / Transport**: Browser SSE streaming, `thread_id` context binding.
2. **LangGraph Engine**: `retrieve` RAG node, `agent` planner, `MemorySaver` checkpointing, transactional design program state.
3. **Guardrails & Preflight**: F03 B-Rep `isValid()` gate, F07 closed-form analytical beam estimator, `os.killpg` process group isolation.
4. **Headless Solver**: `FreeCADCmd` headless execution, Gmsh Delaunay mesher with 25k node budget guard, CalculiX `ccx` static FEA.
5. **Outcome & Persistence**: F02 envelope (1 error + 1 concrete fix), F06 JSONL run history, 3D tensor spatial node coordinates.

---

## 3. Comprehensive Prompts Per Feature with 3-Column Breakdown
Every single prompt card features:
- **1-Click Prompt Copy** button with instant visual feedback.
- **What Should Happen**: Exact tools executed, parameters passed, revision bumps, and simulation output payload.
- **Engineering Value & Story**: Mechanical engineering context, structural trade-offs, and why it matters in presentations.
- **AI Engineering Teardown**:
  - *Cognitive Pattern* (ReAct, Plan-and-Solve, Stateful Mutation)
  - *Guardrails & Safety* (Preflight bounds, B-Rep gate, node budget guards)
  - *Memory & State* (LangGraph thread state, revision hash commits)
  - *Eval Reference* (Associated tests in `tests/` and cases in `eval/cases.json`)

---

## Verification
- Opened [`demo/demo_catalog.html`](demo/demo_catalog.html) in the default browser.
- Verified interactive priority filtering (P0 / P1 / P2), live text search, SVG vector rendering, and clipboard copy buttons.
- Zero backend test bloat added to the repository.
