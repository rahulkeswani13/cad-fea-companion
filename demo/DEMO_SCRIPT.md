# Demo Script — cad-fea-companion (30-minute performance)

A performance script, not a manual (that's `docs/ARCHITECTURE.md`). Every segment card states the exact
prompt, what should happen, why it matters to a simulation engineer, and the AI-engineering
pattern it demonstrates. Feature IDs (`Fxx`) refer to `docs/PLAN.md`; R1–R7 tags refer to
capability keys in `docs/PLAN.md`.

**Thesis:** *natural language in → physics-solved design decision out* — the agent answers
instantly where physics doesn't need to run, runs real FEA when it does, and always says which
is which.

**Cuts:** Core ≈ 33 min · Extended ≈ 45 min · Full 60–75 min.
**Live-solve budget:** max 4–5 live solves per 30 min (each coarse solve is 1–3 min).
Everything else must come from the surrogate (F12), stored results (F06), or an async solve
you narrate over (F11). This constraint **is** the demo: instant where honest, honest where slow.

**Demo mission:** "Make this UAV arm lighter — without dropping below SF 1.5 *or* letting the
first natural frequency fall under the rotor's excitation." Two objectives, one decision.

---

## Pre-demo checklist (run 10 minutes before)

- [ ] `.env` has `GEMINI_API_KEY`; `/api/health` shows LLM ✅ and FreeCAD ✅
- [ ] Fresh thread in the UI; HITL off (`AGENT_REQUIRE_TOOL_CONFIRM=false`)
- [ ] Precomputed results loaded: `POST /api/results/load_precomputed?case=...` for fallbacks
- [ ] Design programs warm: one solid UAV arm + one lattice arm already built (cached revisions)
- [ ] Surrogate dataset trained (F12) so what-if answers are instant
- [ ] Fallback folder open: screenshots of every segment's expected result + recorded clip of
      segment 10 (freeform) in case live authoring fails
- [ ] Terminal + browser font sizes readable on the projector

---

## Core cut (~33 min, 11 segments)

### 1 — Grounded materials answer (2 min) — *demoable today*
- **Prompt:** `What yield strength should I assume for aluminum 6061-T6?`
- **What happens:** Answer ~276 MPa **with citations** to `docs/` snippets. Follow up:
  `And for 7075-T6?` → the agent states what the corpus does and doesn't support rather than
  inventing a number.
- **Significance:** An engineering agent that never invents material data — the failure mode
  everyone fears about LLMs in engineering.
- **AI-engineering lesson:** retrieval-grounded answering with an anti-hallucination contract.
- **Keys:** R1 · **Features:** existing RAG; upgraded by F14/F15.
- **Risk/fallback:** none (local).

### 2 — Flagship part, solid baseline + pre-flight estimate (3 min) — needs F26, F07
- **Prompt:** `Create a solid aluminum UAV arm and set up the 120 N tip load, 14,000 rpm motor.`
- **What happens:** `create_uav_arm` builds the arm (root boss, tapered arm, motor ring). Before
  the solve, a **pre-flight analytical estimate** appears: expected tip deflection and max
  stress from beam theory, with the stated assumption set.
- **Significance:** Physics-first behavior — the agent estimates before it simulates, the way a
  real engineer sanity-checks.
- **AI-engineering lesson:** cheap analytical surrogates as a pre-solve gate; expected-vs-actual.
- **Keys:** R2, R3 · **Features:** F26, F07.
- **Risk/fallback:** cached build from checklist; show STEP in viewer.

### 3 — Async solve + architecture narrated over it (3 min) — needs F11, F05
- **Prompt:** `Solve it.`
- **What happens:** The solve returns an **`operation-1` handle immediately**; status streams
  phases (mesh → solve → publish). While it runs, narrate the **frozen tool surface** visible in
  the trace: this turn exposes solve/analysis tools only, because geometry exists — the surface
  is scoped per turn and per domain, vibecad-style.
- **Significance:** A minute-long solver doesn't freeze the conversation — and the agent's tool
  surface is a deliberate contract, not a firehose.
- **AI-engineering lesson:** async operation handles; scoped, state-aware tool declarations.
- **Keys:** R1, R4 · **Features:** F11, F05.
- **Risk/fallback:** if solve hangs: `read_operation` shows live phase, then pivot to precomputed.

### 4 — Edit, don't recreate (3 min) — needs F04
- **Prompt:** `Set cell size to 12 mm and strut radius to 1.8 mm, rebuild.`
- **What happens:** `update_design_program` merges the patch, shows **revision r2**, rebuilds
  only what changed. The trace shows a parameter patch — not a from-scratch create.
- **Significance:** Design iteration is parametric editing with history — this is what
  "prompt-driven execution" means in a simulation product.
- **AI-engineering lesson:** params-as-source with revision tokens; no-op edits return
  `current`, never an error.
- **Keys:** R1, R2 · **Features:** F04.
- **Risk/fallback:** none (cached path).

### 5 — Deliberate failure → one error, one correction, self-repair (4 min) — needs F02, F03, F13
- **Prompt:** `Set strut radius to 0.8 mm and rebuild.`
- **What happens:** B-Rep/mesh validation **fails fast** with exactly one plain-language error
  and **one concrete correction** ("strut radius 0.8 mm below meshable minimum 1.5 mm — increase
  `strut_radius_mm`"). The accepted revision r2 is untouched. The agent then repairs itself:
  proposes 1.8 mm, rebuilds, continues. You show the failure class table in `docs/repair_loop.md`.
- **Significance:** Failures are first-class product surfaces — this is what operational
  excellence looks like for agent tooling.
- **AI-engineering lesson:** tool outcome contract (one error + one correction); failed
  candidates never clobber accepted state; repair loop with failure taxonomy.
- **Keys:** R4, R6 · **Features:** F02, F03, F13.
- **Risk/fallback:** the failure itself is scripted (0.8 mm always fails) — the safest segment.

### 6 — The decision loop: two objectives (3 min) — needs F26, F27, F12
- **Prompt:** `Compare solid vs lattice arms — lightest with SF ≥ 1.5 AND first mode above 240 Hz.`
- **What happens:** The compare tool sweeps variants (mass, max von Mises, SF, **first natural
  frequency**) and returns a recommendation with the numbers — e.g. "X-truss at 12 mm cells:
  34% lighter, SF 1.7, first mode 262 Hz — meets both."
- **Significance:** **This is the USP.** Not "AI runs a simulation" — AI makes the engineering
  decision across a design space with multiple constraints. Neither text-to-cad nor vibecad
  demos do this; it's a design-performance analysis loop in miniature.
- **AI-engineering lesson:** multi-objective decision loop over parametric variants.
- **Keys:** R2, R3 · **Features:** F26, F27, F12 (stored results make this instant).
- **Risk/fallback:** precomputed comparison table.

### 7 — Material what-if: instant + honest (3 min) — needs F09, F12
- **Prompt:** `What if the arm were Ti-6Al-4V instead?`
- **What happens:** The **surrogate answers in seconds** — mass, SF, frequency shift — labeled
  `estimate (surrogate, ±X%)`. Optionally kick a real FEA confirm in the background.
- **Significance:** DoE-speed exploration without pretending the surrogate is the solver. The
  honesty label is the product decision.
- **AI-engineering lesson:** ML surrogate + verification-scope honesty (from vibecad's
  `validation_scope` pattern).
- **Keys:** R1, R5 · **Features:** F09, F12.
- **Risk/fallback:** cached surrogate predictions.

### 8 — Design-space map (3 min) — needs F12
- **Prompt:** `Map SF and first frequency vs strut radius from 1.2 to 3.5 mm.`
- **What happens:** A chart returns in seconds — the feasible window between the SF floor and
  the frequency floor is visible; the agent names the feasible band and suggests the optimum.
- **Significance:** Turns a week of parametric studies into a sentence — an ML
  surrogate story, running on your laptop.
- **AI-engineering lesson:** surrogate-driven DoE with visual output; bounded, verifiable claims.
- **Keys:** R1, R5 · **Features:** F12 (+F16 render).
- **Risk/fallback:** pre-rendered chart.

### 9 — Ask the results, then look at them (3 min) — needs F06, F16
- **Prompt:** `Where is the stress concentrated in the lattice variant?`
- **What happens:** `query_results` answers from stored run history (root boss fillet region,
  values, vs solid). Then the agent **renders the stress plot (matplotlib) and looks at it** —
  multimodal review — confirming the hotspot matches the query and flagging anything odd.
- **Significance:** Result querying without re-solving, plus an agent that visually verifies its
  own claims — deterministic checks *and* a mandatory look, text-to-cad's snapshot rule applied
  to FEA.
- **AI-engineering lesson:** structured result store; multimodal self-verification.
- **Keys:** R2, R5 · **Features:** F06, F16.
- **Risk/fallback:** saved plot image.

### 10 — Gyroid heat sink thermal what-if (3 min) — needs F28 (else swap: freeform/backup)
- **Prompt:** `Now a different physics: gyroid heat sink, 5 W chip on the base — how much better
  than straight fins at holding base temperature?`
- **What happens:** Gyroid TPMS variant (microgen) vs fin baseline; conduction study results;
  answer with honest scope (conduction only, no convection coefficient claim beyond the stated
  boundary assumption).
- **Significance:** New lattice class + new physics class in one breath — the agent is not a
  one-trick statics tool.
- **AI-engineering lesson:** analysis-type abstraction in the solve pipeline; scope honesty.
- **Keys:** R3 · **Features:** F28 (+F27 plumbing).
- **Risk/fallback:** precomputed case; or swap this segment for the recorded freeform
  "build a simple chair" clip (F17).

### 11 — Architecture wrap + what was NOT verified (2 min)
- **Prompt:** `Summarize what we established today and what we didn't.`
- **What happens:** The agent recaps: which numbers came from CalculiX, which from the
  surrogate, which from beam theory; what mesh sizes; and explicitly lists what was **never
  checked** (fatigue, buckling, joint behavior).
- **Significance:** The honesty contract as the closer — the answer an engineering
  organization can actually trust.
- **AI-engineering lesson:** verification-scope reporting as a first-class output.
- **Keys:** R4, R6 · **Features:** F02/F06/F12 metadata.
- **Risk/fallback:** none.

---

## Extended cut (+12 min)

- **E1 — Mesh convergence study** (needs F08): `run_convergence_study` on the lattice arm;
  narrate KPI convergence and the recommended mesh size while it runs async (4 min).
- **E2 — Off-axis load case** (needs F10): `Solve 200 N at 30° off-axis` — direction is a
  validated parameter, not a fixed pattern (4 min).
- **E3 — Brake pedal onboarding walkthrough** (demoable today): the original grounding →
  create → solve → compare flow on the tutorial part; shows where the project started (4 min).

## Full cut (60–75 min)

- Core + Extended, plus:
- **FU1 — Freeform "build a simple chair"** (needs F17): agent-authored FreeCAD Python,
  validated, published — with the recorded-clip fallback (5 min).
- **FU2 — External agent via MCP** (needs F18): Claude Code drives the companion's tools
  through the MCP server — same contracts, different client (5 min).
- **FU3 — text-to-cad composition** (needs F20): t2c generates a bracket STEP, companion
  solves and recommends on it — the "brain on top of hands" story (5 min).

---

## If-you-only-remember-three-things (interview recap)

1. Segment 6 — the multi-objective decision loop. Nobody else's demo does this.
2. Segment 5 — failure with one error + one correction and self-repair. Reliability is the moat.
3. Segment 7/8 — surrogate speed with honest labels. That's the machine-learning
   story, live.
