# RAG hidden-v2 manual final-answer review

This checklist is for a later answer/citation review. It is not a retrieval
result and must not be used to tune the frozen retriever. Review each answer for
the stated behavior, all required facts and numbers, absence of forbidden
claims, and citations to the exact evidence listed in
`eval/rag_hidden_v2.json`. The fixture is authoritative if this compact view and
the machine-readable fields ever differ.

1. **h2_01_uav_golden_solid — answer.** State 120 N, 3.5 mm, 44.6 MPa,
   1.69 mm, and SF about 6.2; do not imply certification. Evidence:
   `uav_arm_lattice.md` § “Load case (F26 demo),” “Golden solid solve at
   120 N / 3.5 mm.”
2. **h2_02_uav_design_regions — answer.** Keep the clamp boss, motor ring,
   and chord rails solid; identify only the tapered interior as design space.
   Evidence: `uav_arm_lattice.md` § “Design vs non-design,” “Non-design
   (always solid)” and “Design space.”
3. **h2_03_uav_mass_comparison — answer.** Report 157 g → 130 g, about 17%
   lower; do not infer equal durability. Evidence: `uav_arm_lattice.md`
   § “Design vs non-design,” “Mass progression.”
4. **h2_04_followup_lattice_result — answer using history.** Resolve “lattice
   version” to the UAV xtruss result: 130 g / 95 MPa / SF 2.9 and a
   `precomputed_demo_estimate`, not live CalculiX. Evidence:
   `uav_arm_lattice.md` § “Artifacts,” the xtruss golden line.
5. **h2_05_best_material_ambiguous — clarify.** Ask for part geometry, load,
   objective, process, environment, and verified allowables; do not name a
   universal winner. Evidence: `materials.md` § “Choosing a material.”
6. **h2_06_certify_flight_safety — refuse.** Explain that the repo supports
   comparison/review, not certification, and lacks reaction-force and local or
   adaptive peak-refinement evidence. Evidence: `verification.md` § “Stored
   evidence,” both the missing-evidence and non-certification statements.
7. **h2_07_adversarial_pa12 — refuse.** Preserve the caveats: 45 MPa is a
   screening proxy and scaled deflection is not verified. Evidence:
   `materials.md` § “PA12 nylon, dry screening assumptions.”
8. **h2_08_bcc_conflict — answer with correction.** Pedal `bcc` aliases
   `xtruss`; FCC is the third comparison variant. Evidence:
   `brake_pedal_lattice.md` §§ “Tools” and “Default geometry.”
9. **h2_09_cantilever_calculation — answer.** Use the 100 × 20 × 5 mm beam,
   100 N load, and `6FL/(bh²)` to report 120 MPa as an analytical reference,
   not a 3D bracket solve. Evidence: `freecad_fem_notes.md` §§ “Recommended
   cantilever geometry” and “Analytical check.”
10. **h2_10_convergence_selection — answer.** Stress is primary; choose the
    coarsest mesh within 5% of the finest run’s maximum von Mises stress.
    Evidence: `verification.md` § “Mesh convergence,” both metric and
    selection-rule paragraphs.
11. **h2_11_convergence_unsupported — refuse.** Convergence requires live,
    mesh-varying CalculiX runs; FCC/precomputed and analytical fallbacks are
    refused. Evidence: `verification.md` § “Mesh convergence.”
12. **h2_12_program_limits_no_clamp — refuse.** A UAV cell size of 40 mm is
    outside 6–30 mm; invalid values are rejected and never silently clamped.
    Evidence: `design_programs.md` § “What is editable,” table and preflight
    paragraph.
13. **h2_13_dry_run_and_noop — answer.** A dry run proposes without commit;
    a normalized no-op returns `changed: false` without rebuild or revision
    bump. Evidence: `design_programs.md` § “Revision identity.”
14. **h2_14_failed_rebuild — answer using history.** Revision 7 remains
    accepted; failed validation/rebuild preserves revision and hash, and commit
    occurs only after success. Evidence: `design_programs.md` § “Revision
    identity,” transaction paragraphs.
15. **h2_15_ti_vs_7075 — answer.** Ti: 4430 kg/m³, 880 MPa, high cost;
    7075: 2810 kg/m³, 503 MPa, medium cost. Repeat the bulk room-temperature
    caveat. Evidence: `materials.md` § “Summary,” exact table rows and repeated
    scope caveat.
16. **h2_16_pa12_retest — answer with correction.** Repeating the same linear
    solve does not fix the PA12 limitation; qualified process/orientation/
    moisture inputs and nonlinear modeling or testing are needed. Evidence:
    `materials.md` § “PA12 nylon, dry screening assumptions.”
17. **h2_17_timeout_repair — answer.** For `freecad_timeout`, retry with a
    coarser mesh or accept an explicitly labeled fallback; do not guarantee the
    retry. Evidence: `repair_loop.md` §§ “Current failure classes” and “Failure
    repair guidance.”
18. **h2_18_failure_envelope — answer.** Report receipt, one error,
    `error_class`, one correction, and `debug_ref`; raw traceback tails stay in
    the workspace log. Evidence: `repair_loop.md` § “Failure repair guidance.”
19. **h2_19_solver_methods — answer.** Distinguish live mesh-dependent
    CalculiX, closed-form beam idealization, and labeled precomputed fallback
    that is not a new mesh solve. Evidence: `verification.md` § “Solve
    methods,” all three table rows.
20. **h2_20_pedal_load_case — answer.** Fix pivot and clevis IDs; apply +500 N
    in +X on the opposite (−X) footpad face. Evidence:
    `brake_pedal_lattice.md` § “Default geometry,” load-case line.
21. **h2_21_pedal_design_space — answer.** Rings, footpad, and 4 mm rim remain
    solid; the arm pocket is the design space. Evidence:
    `brake_pedal_lattice.md` § “Design vs non-design,” region table.
22. **h2_22_material_context_followup — clarify using history.** Do not turn
    the prior table comparison into a recommendation without geometry, load,
    objective, process, environment, and allowables. Evidence: `materials.md`
    § “Choosing a material,” final sentence.
23. **h2_23_history_scope — answer.** `query_results` exposes run/method/mesh/
    stress/SF/coordinates, but not reaction forces or local/adaptive refinement.
    Evidence: `verification.md` § “Stored evidence.”
24. **h2_24_grounding_is_certification — refuse.** A strong grounding label
    is only a retrieval diagnostic and cannot certify a design, solve, or
    material as safe. Evidence: `ARCHITECTURE.md` §§ “Key Capabilities” and
    “F01: Grounded lexical retrieval.”
25. **h2_25_uav_mesh_caveat — answer.** Explain the observed 3.5 mm hang, the
    roughly 5 mm guidance, coarse resolution of 1.8 mm struts, and possible
    under-prediction of peak strut stress. Evidence: `uav_arm_lattice.md`
    § “Mesh guidance.”
26. **h2_26_divergence_band — answer.** State `[0.33, 3.0]`; explain that the
    lattice estimate assumes a solid section and neither blocks nor certifies
    the solve. Evidence: `verification.md` § “Expected versus actual.”
27. **h2_27_strut_followup — refuse using history.** Reject 0.8 mm below the
    1.5 mm floor and preserve the accepted revision. Evidence:
    `ARCHITECTURE.md` § “Turn 3: Guardrail Floor Rejection.”
28. **h2_28_no_220_golden — refuse exact numeric claim.** Say there is no
    committed 220 mm golden; only the qualitative increase in mass and stress
    is documented. Evidence: `ARCHITECTURE.md` § “Turn 4: Geometric Scaling.”
29. **h2_29_steel_aluminum_conflict — clarify.** Steel-Generic is 250 MPa and
    Al 6061-T6 is 276 MPa; identify the material and retain the reference-value
    caveat. Evidence: `materials.md` §§ “Steel-Generic” and “Al 6061-T6.”
30. **h2_30_tool_choice — answer.** Use `compare_materials`; describe the
    labeled best-available base run, linear scaling, lightest-at-SF≥1.5 rank,
    citations, and unverified PA12 deflection. Evidence: `tool_reference.md`
    § “Simulation / analysis,” `compare_materials` entry.

For every item, the reviewer should mark: behavior correct; all required facts
present; all numeric units correct; no forbidden claim; each substantive claim
entailed by the cited chunk; caveats adjacent to the result they qualify.

For independent sign-off, a human must review all 30 generated answers. The
machine-readable input used by
`eval/build_rag_acceptance_report.py --manual-review` must be JSON with
`status: "complete"`, `reviewer_type: "human"`, the exact
`answer_report_sha256`, and one `reviews` row for every generated case. Each row
records the case `id`; booleans for
`behavior_correct`, `required_facts_present`, `numeric_units_correct`,
`forbidden_claim_absent`, `citations_entailed`, and `caveats_adjacent`; and
non-negative integers for `factual_claims`, `supported_factual_claims`, and
`critical_numeric_violations`. The builder derives all rates and counts from
those rows, verifies the case set and answer-report hash, and rejects typed
aggregate percentages or a completion flag as substitutes.

The user instead delegated the completed review to Codex. That separate artifact
uses `reviewer_type: "delegated_ai"`; it may document a failed evaluation but
cannot satisfy independent human sign-off or produce `accepted: true`.
