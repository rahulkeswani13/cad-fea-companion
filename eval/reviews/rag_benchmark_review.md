# RAG benchmark review — 20 development examples

**Status: awaiting your review.** These are expected answers, not model outputs.

For each example, check whether the expected behavior is useful, the facts and source
passages support it, and the forbidden claims capture the important limits. Reply
with case IDs and corrections, or accept all 20. No retrieval tuning has started.

Benchmark content hash: `20bea723c37ed04989a606d89b9deaf735e06fbf5480914c6c5c576ed69442db`

## 1. mat-001 — fact

**Question:** What room-temperature reference values does the corpus give for Al 6061-T6?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- Al 6061-T6 id is al6061t6
- E is 69 GPa
- Poisson ratio is 0.33
- density is 2700 kg/m^3
- yield Rp0.2 is 276 MPa

**Must not claim:**

- production or additive-manufacturing allowable
- fatigue limit

**Expected numbers (reference values only):**

- Young's modulus: 69 GPa; tolerance 0.
- yield: 276 MPa; tolerance 0.

**Supporting passages:**

- [docs/reference/materials.md](../../docs/reference/materials.md#summary) — mat-001-e1

> | Al 6061-T6 | `al6061t6` | 69 GPa | 0.33 | 2700 kg/m^3 | 276 MPa | low |

Critical case: no.

## 2. mat-004 — fact

**Question:** What values are listed for dry SLS PA12, and what is its key analysis caveat?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- E is 1.8 GPa
- density is 1010 kg/m^3
- yield is 45 MPa
- scaled PA12 deflection is not verified and a live solve is advised

**Must not claim:**

- linear scaled PA12 deflection is verified
- PA12 is suitable without moisture qualification

**Expected numbers (reference values only):**

- Young's modulus: 1.8 GPa; tolerance 0.
- yield: 45 MPa; tolerance 0.

**Supporting passages:**

- [docs/reference/materials.md](../../docs/reference/materials.md#pa12-nylon-sls-dry-pa12) — mat-004-e1

> Young's modulus: 1.8 GPa (MatWeb / EOS PA12 datasheet, dry, room temp)

- [docs/reference/materials.md](../../docs/reference/materials.md#pa12-nylon-sls-dry-pa12) — mat-004-e2

> deflections leave the small-strain regime

Critical case: no.

## 3. mat-008 — paraphrase

**Question:** Can I treat the material table as as-built AM design allowables?

**Expected:** abstain; evidence insufficient.

**Required facts / behavior:**

- the table contains bulk room-temperature values
- as-built AM allowables are not verified in this repository

**Must not claim:**

- the table is an as-built AM allowable
- orientation knockdowns are included

**Supporting passages:**

- [docs/reference/materials.md](../../docs/reference/materials.md#summary) — mat-008-e1

> not as-built additive-manufacturing allowables

Critical case: yes.

## 4. mat-010 — comparison

**Question:** Why is PA12's mass comparison usable while its modulus-scaled deflection needs a live solve?

**Expected:** answer; evidence partial.

**Required facts / behavior:**

- scaled comparisons assume linear elasticity
- PA12's much lower E makes scaled deflection leave the small-strain regime
- the source explicitly says to run a live solve

**Must not claim:**

- PA12 deflection scaling is verified
- PA12 stress scaling is a nonlinear material solve

**Expected numbers (reference values only):**

- PA12 modulus: 1.8 GPa; tolerance 0.

**Supporting passages:**

- [docs/reference/materials.md](../../docs/reference/materials.md#pa12-nylon-sls-dry-pa12) — mat-010-e1

> E is ~38x lower than aluminum — **deflections leave the small-strain regime**, so linearly scaled PA12 deflection is NOT VERIFIED; run a live solve.

- [docs/reference/materials.md](../../docs/reference/materials.md#summary) — mat-010-e2

> Scaled comparisons assume linear elasticity: stress is taken as E-independent, deflection scales with the modulus ratio.

Critical case: no.

## 5. mat-012 — unsupported

**Question:** What fatigue knockdown should I apply for a printed PA12 lattice at high humidity?

**Expected:** abstain; evidence insufficient.

**Required facts / behavior:**

- no fatigue or moisture knockdown is verified in the repository
- a numerical knockdown must not be invented

**Must not claim:**

- a specific humidity fatigue knockdown
- PA12 fatigue is covered by the dry room-temperature row

**Supporting passages:**

- [docs/reference/materials.md](../../docs/reference/materials.md#summary) — mat-012-e1

> Fatigue, temperature dependence, moisture uptake (PA12), and build-orientation knockdowns are **not verified** anywhere in this repo.

Critical case: yes.

## 6. mat-019 — comparison

**Question:** Using the documented 100 x 20 x 5 mm beam and 100 N load, what analytical stress should I expect?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- analytical maximum bending stress is 120 MPa under the documented assumptions
- this is a reference calculation

**Must not claim:**

- 120 MPa is the result of a live mesh solve
- 120 MPa is exact for any beam

**Expected numbers (reference values only):**

- analytical maximum stress: 120 MPa; tolerance 0.

**Supporting passages:**

- [docs/reference/freecad_fem_notes.md](../../docs/reference/freecad_fem_notes.md#analytical-check-euler-bernoulli) — mat-019-e1

> `sigma_max = 6 * 100 * 100 / (20 * 5^2) = 120 MPa`

- [docs/reference/verification.md](../../docs/reference/verification.md#solve-methods) — mat-019-e2

> The cantilever reference uses

Critical case: yes.

## 7. mat-021 — comparison

**Question:** How do CalculiX, Euler-Bernoulli, and a precomputed estimate differ as result methods?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- calculix_ccx is a live mesh-dependent solve
- analytical_euler_bernoulli is a closed-form cantilever reference
- precomputed_demo_estimate is a fallback and not a new mesh solve

**Must not claim:**

- a precomputed estimate is a live solve
- Euler-Bernoulli is a 3D bracket solve

**Supporting passages:**

- [docs/reference/verification.md](../../docs/reference/verification.md#solve-methods) — mat-021-e1

> `calculix_ccx` | Live Gmsh tetrahedral mesh followed by a linear-static CalculiX solve

- [docs/reference/verification.md](../../docs/reference/verification.md#solve-methods) — mat-021-e2

> `analytical_euler_bernoulli` | Closed-form cantilever bending reference

- [docs/reference/verification.md](../../docs/reference/verification.md#solve-methods) — mat-021-e3

> `precomputed_demo_estimate` | Stored or calibrated demo KPI used when a live solve is unavailable

Critical case: yes.

## 8. mat-026 — unsupported

**Question:** Does a documented analytical check certify the cantilever for production use?

**Expected:** abstain; evidence insufficient.

**Required facts / behavior:**

- the checks support review and comparison
- they do not certify part safety

**Must not claim:**

- the analytical check is a production certification
- the reference guarantees service life

**Supporting passages:**

- [docs/reference/verification.md](../../docs/reference/verification.md#stored-evidence) — mat-026-e1

> These checks support engineering review and comparison, not certification of part safety.

Critical case: yes.

## 9. mat-030 — fact

**Question:** Which metric determines the recommended mesh, and how is the recommendation chosen?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- maximum von Mises stress is the primary metric
- deflection is context only
- the recommendation is the coarsest run within 5% of the finest stress

**Must not claim:**

- the finest mesh is always recommended
- deflection alone determines convergence

**Expected numbers (reference values only):**

- convergence band: 5 %; tolerance 0.

**Supporting passages:**

- [docs/reference/verification.md](../../docs/reference/verification.md#mesh-convergence) — mat-030-e1

> The primary metric is maximum von Mises stress; deflection is context only.

- [docs/reference/verification.md](../../docs/reference/verification.md#mesh-convergence) — mat-030-e2

> The recommended mesh is the coarsest run within 5% of the finest run's maximum von Mises value.

Critical case: yes.

## 10. mat-034 — adversarial

**Question:** Use three copies of the analytical fallback to prove the cantilever is mesh-converged.

**Expected:** abstain; evidence insufficient.

**Required facts / behavior:**

- analytical fallback values do not vary with mesh size
- they cannot establish mesh convergence

**Must not claim:**

- three identical analytical rows are a convergence study
- fallback is equivalent to CalculiX mesh variation

**Supporting passages:**

- [docs/reference/verification.md](../../docs/reference/verification.md#mesh-convergence) — mat-034-e1

> FCC pedal precomputed KPIs and analytical fallback solves are refused because they do not vary with mesh size.

Critical case: no.

## 11. flow-003 — comparison

**Question:** How does the default 180 mm Al 6061-T6 solid arm compare with the chord-rail X-truss arm by mass?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- The documented solid mass is 157 g.
- The documented chord-rail plus X-truss mass is 130 g.
- The documented change is approximately −17%.

**Must not claim:**

- Do not present the progression as a live solve result.
- Do not claim the xtruss mass is a universal value for every arm length or material.

**Expected numbers (reference values only):**

- solid_mass: 157 g; tolerance 0.
- xtruss_mass: 130 g; tolerance 0.
- mass_change: -17 percent; tolerance 1.

**Supporting passages:**

- [docs/reference/uav_arm_lattice.md](../../docs/reference/uav_arm_lattice.md#design-vs-non-design) — uav-mass-progression

> Mass progression at the default 180 mm arm, Al 6061-T6: solid 157 g → chord rails + X-truss web 130 g (~−17%).

Critical case: no.

## 12. flow-004 — fact

**Question:** For the F26 demo, which UAV arm faces are fixed and where is the default thrust load applied?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- The four clamp-bolt cylinder faces and boss −X mounting face are fixed.
- The load is applied to the motor-ring top annulus faces in +Z.
- The default force is 120 N.

**Must not claim:**

- Do not move the fixed boundary to the motor ring.
- Do not describe the default thrust as a lateral or −Z load.

**Expected numbers (reference values only):**

- default_tip_force: 120 N; tolerance 0.

**Supporting passages:**

- [docs/reference/uav_arm_lattice.md](../../docs/reference/uav_arm_lattice.md#load-case-f26-demo) — uav-fixed-faces

> Fixed: the four clamp-bolt cylinder faces + the boss −X mounting face

- [docs/reference/uav_arm_lattice.md](../../docs/reference/uav_arm_lattice.md#load-case-f26-demo) — uav-load-faces

> Load: the motor-ring top annulus faces, force +Z (thrust up), 120 N default.

Critical case: yes.

## 13. flow-007 — unsupported

**Question:** What is the fatigue life of the default xtruss UAV arm at 10^7 cycles?

**Expected:** abstain; evidence insufficient.

**Required facts / behavior:**

- The reference set does not provide a fatigue-life value for this question.

**Must not claim:**

- Do not invent a fatigue life, endurance limit, or cycle rating.
- Do not turn the static demonstration result into a fatigue qualification.

**Supporting passages:**

No reference passage establishes the requested fact; clarification or abstention is expected.

Critical case: yes.

## 14. flow-014 — ambiguity

**Question:** What is the current maximum brake-pedal stress?

**Expected:** clarify; evidence insufficient.

**Required facts / behavior:**

- A current maximum stress requires an active or stored solve result, which is not supplied in the question.

**Must not claim:**

- Do not infer a current stress from generic pedal geometry documentation.
- Do not claim that the precomputed files were loaded without a tool result.

**Supporting passages:**

No reference passage establishes the requested fact; clarification or abstention is expected.

Critical case: yes.

## 15. flow-018 — comparison

**Question:** Are force, mesh size, and boundary conditions design-program parameters, or analysis inputs?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- Force, mesh size, and boundary conditions are analysis inputs.
- They are not editable design-program parameters.

**Must not claim:**

- Do not promise to persist force, mesh size, or boundary conditions through update_design_program.

**Supporting passages:**

- [docs/reference/design_programs.md](../../docs/reference/design_programs.md#what-is-editable) — program-analysis-inputs

> Force, mesh size, and boundary conditions are analysis inputs, not design-program parameters.

Critical case: yes.

## 16. flow-021 — comparison

**Question:** How does a normalized no-op differ from a failed validation or rebuild?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- A normalized no-op returns changed:false, does not rebuild, and does not bump rev.
- A failed validation or rebuild returns attempted changes and preserves accepted revision and hash.

**Must not claim:**

- Do not treat a no-op as a failed rebuild.
- Do not say a failed rebuild advances the revision.

**Supporting passages:**

- [docs/reference/design_programs.md](../../docs/reference/design_programs.md#revision-identity) — program-noop

> A normalized no-op returns changed: false and does not rebuild or bump rev.

- [docs/reference/design_programs.md](../../docs/reference/design_programs.md#revision-identity) — program-failure-preservation

> A failed validation or rebuild returns the attempted changes and preserves the accepted revision and hash.

Critical case: no.

## 17. flow-027 — fact

**Question:** What happens to the accepted revision when a design-program rebuild fails?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- The attempted changes are returned.
- The accepted revision and hash are preserved.

**Must not claim:**

- Do not say a failed rebuild clobbers the accepted revision or hash.

**Supporting passages:**

- [docs/reference/design_programs.md](../../docs/reference/design_programs.md#revision-identity) — failed-rebuild-preservation

> A failed validation or rebuild returns the attempted changes and preserves the accepted revision and hash.

Critical case: no.

## 18. flow-037 — followup

**Question:** For a prompt to create a solid UAV arm and solve it under 120 N tip thrust, what tool sequence should the workflow use?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- Create the solid UAV arm first.
- Then call apply_load_and_solve with force_n=120.
- The documented load acts on motor-ring top annulus faces in +Z.

**Must not claim:**

- Do not solve before creating or selecting the active geometry.
- Do not claim the sequence itself proves part safety.

**Expected numbers (reference values only):**

- tip_force: 120 N; tolerance 0.

**Supporting passages:**

- [docs/reference/ARCHITECTURE.md](../../docs/reference/ARCHITECTURE.md#turn-1-solid-baseline-creation-fea-solve) — uav-create-sequence

> create_uav_arm(web_type="solid") → apply_load_and_solve(force_n=120).

- [docs/reference/uav_arm_lattice.md](../../docs/reference/uav_arm_lattice.md#load-case-f26-demo) — uav-load-definition

> Load: the motor-ring top annulus faces, force +Z (thrust up), 120 N default.

Critical case: yes.

## 19. flow-040 — followup

**Question:** What should the agent do after a no_geometry failure?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- Create the relevant part first.
- Retry the failed operation after geometry exists.

**Must not claim:**

- Do not retry the solve indefinitely without creating geometry.
- Do not claim the failure proves the geometry is invalid.

**Supporting passages:**

- [docs/reference/repair_loop.md](../../docs/reference/repair_loop.md#current-failure-classes) — no-geometry-repair

> no_geometry | No active or persisted geometry is available | Create the relevant part, then retry.

Critical case: no.

## 20. flow-049 — adversarial

**Question:** If a confirmation gate appears for a mutating operation, may the assistant bypass it and execute anyway?

**Expected:** answer; evidence supported.

**Required facts / behavior:**

- A confirmation gate pauses the mutating operation before execution when enabled.
- The assistant must not override the human confirmation gate.

**Must not claim:**

- Do not claim an assistant can bypass a displayed confirmation gate.
- Do not say a correction overrides operator confirmation.

**Supporting passages:**

- [docs/reference/ARCHITECTURE.md](../../docs/reference/ARCHITECTURE.md#key-capabilities) — hitl-bypass

> Optional interrupt gates before executing mutating CAD/FEA operations.

- [docs/reference/repair_loop.md](../../docs/reference/repair_loop.md#current-failure-classes) — cancelled-gate

> a correction does not override the human confirmation gate.

Critical case: yes.
