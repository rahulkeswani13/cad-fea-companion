"""LangChain tool schemas for bind_tools; execution still goes through call_tool.

H3: the canonical arg models (with enforced ranges) live in
``companion.tools.tool_schemas`` — this module re-exports them so existing
imports keep working, and TOOL_SPECS/program floors derive from the same
models.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from companion.tools.tool_schemas import (  # noqa: F401 — public re-exports
    ApplyLoadArgs,
    CompareMaterialsArgs,
    CreateBrakePedalArgs,
    CreateCantileverArgs,
    CreateUavArmArgs,
    EmptyArgs,
    GetDesignProgramArgs,
    QueryResultsArgs,
    RunConvergenceStudyArgs,
    UpdateDesignProgramArgs,
)


def _noop(**_kwargs: Any) -> str:
    """Schema-only stub; the graph tools node calls cad_fea.call_tool."""
    return "{}"


def get_langchain_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            func=_noop,
            name="create_brake_pedal",
            description=(
                "Create an Al brake-pedal lattice bracket (pivot + clevis + footpad) "
                "with web_type solid|xtruss|fcc lattice fill; open FreeCAD GUI."
            ),
            args_schema=CreateBrakePedalArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="get_lattice_metrics",
            description=(
                "Return relative density, volumes, and mass for the current "
                "brake-pedal geometry."
            ),
            args_schema=EmptyArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="compare_brake_pedal_variants",
            description=(
                "Compare solid vs X-truss vs FCC brake-pedal mass, stress, deflection; "
                "recommend lightest with SF>=1.5."
            ),
            args_schema=EmptyArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="compare_materials",
            description=(
                "Compare materials (Al 6061-T6, Al 7075-T6, Ti-6Al-4V, PA12, steel) "
                "for the current part: mass, stress, SF vs each yield, scaled "
                "deflection, with citations. Use for 'Ti vs Al' questions; "
                "PA12 deflection is flagged not verified."
            ),
            args_schema=CompareMaterialsArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="create_uav_arm",
            description=(
                "Create the flagship UAV arm (root clamp boss + tapered arm + "
                "tip motor ring) with web_type solid|xtruss; export STEP/STL "
                "and open FreeCAD GUI. Demo load case: 120 N tip thrust."
            ),
            args_schema=CreateUavArmArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="create_cantilever",
            description=(
                "Create a rectangular cantilever beam (mm), export STEP/STL, "
                "and open the model in the FreeCAD GUI."
            ),
            args_schema=CreateCantileverArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="apply_load_and_solve",
            description=(
                "Apply load (N), mesh with Gmsh, solve with CalculiX inside FreeCAD, "
                "save results, and open the FEM document. Requires create_brake_pedal "
                "or create_cantilever first."
            ),
            args_schema=ApplyLoadArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="get_max_von_mises",
            description="Return max von Mises stress (MPa) from the latest solve.",
            args_schema=EmptyArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="query_results",
            description=(
                "Query the stored per-run solve history: latest run in full "
                "(mass, max von Mises + its location, deflection, mesh size, "
                "method flag, expected-vs-actual divergence) plus a compact list "
                "of recent runs. 'Where is stress concentrated' = "
                "max_vm_location_mm of the latest run."
            ),
            args_schema=QueryResultsArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="run_convergence_study",
            description=(
                "Mesh convergence study: 2-3 live CalculiX solves at refining "
                "mesh sizes, then the recommended mesh = coarsest within 5% "
                "of the finest max von Mises. Synchronous and headless; "
                "costs roughly 2-3 solves. Refuses setups without live "
                "solves (fcc pedal, FreeCAD absent)."
            ),
            args_schema=RunConvergenceStudyArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="open_in_freecad",
            description="Launch FreeCAD GUI with the latest CAD/FEM document.",
            args_schema=EmptyArgs,
        ),
    ]


# Tools that open/mutate FreeCAD GUI — candidates for HITL confirm
FREECAD_MUTATING_TOOLS = frozenset(
    {
        "create_brake_pedal",
        "create_uav_arm",
        "create_cantilever",
        "apply_load_and_solve",
        "run_convergence_study",
        "open_in_freecad",
    }
)
