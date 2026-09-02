"""H7: prompt surgery — SYSTEM_PROMPT carries no hardcoded figures/defaults.

Answers must derive numbers from CAD state, tool results, or retrieved
context. This pins the surgery so figures can't creep back into the prompt
(the "teaching to your own test" failure mode).
"""

from __future__ import annotations

from companion.agent.graph import SYSTEM_PROMPT

_FORBIDDEN_SUBSTRINGS = (
    # stress references
    "276 MPa",
    "120 MPa",
    "~120",
    "(~276",
    # per-part load defaults
    "+500 N",
    "500 N",
    "Fx=+500",
    "20000",
    "100 N /",
    # mesh-size defaults
    "2.5 mm",
    "mesh sizes",
    "5/3.5/2.5",
    # restated tool costs
    "2-3 solves",
    # per-part material defaults
    "Al 6061-T6 yield",
    "aluminum brake-pedal",
)

_REQUIRED_SUBSTRINGS = (
    "{cad_state}",
    "{context}",
    "{tools}",
    "do not know",
    "NOT VERIFIED",
    "calculix / analytical",
    "[source]",
    "compare_materials",
    "update_design_program",
    "run_convergence_study",
)


def test_prompt_carries_no_hardcoded_figures_or_defaults():
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle not in SYSTEM_PROMPT, f"figure crept back: {needle!r}"


def test_prompt_keeps_role_slots_and_honesty_rules():
    for needle in _REQUIRED_SUBSTRINGS:
        assert needle in SYSTEM_PROMPT, f"required slot/rule missing: {needle!r}"
    # All format slots resolve (no KeyError from a removed/renamed key).
    rendered = SYSTEM_PROMPT.format(
        cad_state="(none)", context="(none)", tools="[]"
    )
    assert "(none)" in rendered


def test_tool_schemas_carry_what_the_prompt_lost():
    """The figures/defaults must live in the generated tool schemas instead."""
    from companion.tools.cad_fea import TOOL_SPECS

    by_name = {spec["name"]: spec for spec in TOOL_SPECS}
    uav_props = by_name["create_uav_arm"]["parameters"]["properties"]
    assert uav_props["arm_length_mm"]["default"] == 180.0
    assert uav_props["strut_radius_mm"]["minimum"] == 1.5
    pedal_props = by_name["create_brake_pedal"]["parameters"]["properties"]
    assert pedal_props["cell_size_mm"]["default"] == 15.0
