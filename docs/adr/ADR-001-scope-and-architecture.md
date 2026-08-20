# ADR-001: Scope and architecture decisions

Date: 2026-08-15 · Status: accepted

## Context

Study of two reference systems — vibecad (FreeCAD fork with embedded AI; scoped frozen tool
surfaces, source-backed VibeScript programs with revisions, validate-then-publish, MCP,
tool outcome contract) and text-to-cad (installable agent skills; agent-authored build123d
source, deterministic CLIs, repair loop, artifact discipline, mandatory snapshot review) —
plus commercial simulation-assistant feature research.
Project goal: deepen the USP (*natural language in → physics-solved design decision out*)
while building agentic-AI engineering skill.

## Decisions

1. **Evolve this repo; do not fork vibecad.** Forking buys GUI embedding (lowest-value goal)
   at the cost of a 14,600-file C++ codebase and inverted learning (FreeCAD internals instead
   of agent architecture). Integration (MCP, composition) over incorporation.
2. **Stay on the structural / agentic-AI track.** Fluids, C++, CFD, and scientific ML
   are a different investment. Surrogate work (F12) incidentally helps;
   no C++ detours (F25 explicitly last).
3. **Brake pedal demoted to onboarding part.** Two flagship parts added: UAV arm
   (strut lattice + modal; low risk) and heat sink (gyroid TPMS via microgen + thermal;
   showstopper, medium risk).
4. **Adopt vibecad/text-to-cad patterns** (design programs with revisions, outcome contract,
   scoped tool surfaces, repair loop, snapshot review) per `docs/PLAN.md`. The integration
   guide proposing kinematic/COTS/DFM calculator tools was rejected: fabricated attributions
   and a statics error (ignored pushrod angle); only its B-Rep validation idea survives (F03).
5. **New physics comes from FreeCAD's own `femexamples`** (frequency, buckling, thermomech,
   contact, centrifugal — all headless-runnable). Crib, don't invent.
6. **Source-of-truth policy:** parameters (design programs) are authoritative; generated
   geometry and results are derived. GUI edits are out of scope until F23 (Route B:
   detect + mark "diverged from source"; never silent two-way sync).

## Consequences

- All features additive; tool contracts change only via new ADRs.
- Demo depends on P0/P1 landing (see `demo/DEMO_SCRIPT.md` segment table for per-segment deps).
- If microgen TPMS volume-meshing fails inside the FEA pipeline, F28 falls back to strut
  lattices for solving while keeping TPMS for visuals (decided up front to bound the risk).
