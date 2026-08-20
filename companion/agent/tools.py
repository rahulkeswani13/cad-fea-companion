"""LangChain tool schemas for bind_tools; execution still goes through call_tool."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class CreateBrakePedalArgs(BaseModel):
    web_type: Literal["solid", "xtruss", "fcc"] = Field(
        default="xtruss",
        description="Web fill: solid, 2.5D X-truss, or fcc lattice",
    )
    cell_size_mm: float = Field(default=15.0, description="Lattice cell size mm")
    strut_radius_mm: float = Field(
        default=2.5,
        description="X-truss strut thickness mm (or FCC strut radius)",
    )
    material: str | None = Field(
        default=None,
        description=(
            "Material id or alias (al6061t6 default; also al7075t6, ti6al4v, "
            "pa12, steel; 'ti', '7075', 'nylon' accepted)"
        ),
    )
    open_gui: bool = Field(default=False, description="Open FreeCAD GUI after create")


class CreateUavArmArgs(BaseModel):
    web_type: Literal["solid", "xtruss"] = Field(
        default="solid",
        description="Arm fill: solid, or chord rails + exposed X-truss web",
    )
    arm_length_mm: float = Field(default=180.0, description="Arm length mm (120-320)")
    cell_size_mm: float = Field(default=12.0, description="Lattice cell size mm (6-30)")
    strut_radius_mm: float = Field(
        default=1.8,
        description="X-truss strut radius mm (1.5 meshable minimum - 4)",
    )
    material: str | None = Field(
        default=None,
        description=(
            "Material id or alias (al6061t6 default; also al7075t6, ti6al4v, "
            "pa12, steel)"
        ),
    )
    open_gui: bool = Field(default=False, description="Open FreeCAD GUI after create")


class CreateCantileverArgs(BaseModel):
    length_mm: float = Field(default=100.0, description="Beam length in mm")
    width_mm: float = Field(default=20.0, description="Beam width in mm")
    height_mm: float = Field(default=5.0, description="Beam height in mm")
    material: str | None = Field(
        default=None,
        description=(
            "Material id or alias (steel default; also al6061t6, al7075t6, "
            "ti6al4v, pa12)"
        ),
    )
    open_gui: bool = Field(default=False, description="Open FreeCAD GUI after create")


class ApplyLoadArgs(BaseModel):
    force_n: float | None = Field(
        default=None,
        description="Load in newtons (default 500 pedal / 20000 mount / 100 cantilever)",
    )
    mesh_max_size_mm: float | None = Field(
        default=None,
        description="Coarse mesh size mm (default 5 pedal / 4 mount / 2.5 cantilever)",
    )
    open_gui: bool = Field(default=False, description="Open FreeCAD GUI after solve")


class EmptyArgs(BaseModel):
    pass


class QueryResultsArgs(BaseModel):
    part: str | None = Field(
        default=None,
        description="brake_pedal|cantilever, default = active part",
    )
    run_id: str | None = Field(
        default=None,
        description="Optional run id from a previous solve (returns that run only)",
    )
    last_n: int = Field(
        default=10, ge=1, le=50, description="How many recent runs to list"
    )


class CompareMaterialsArgs(BaseModel):
    part: str | None = Field(
        default=None,
        description="brake_pedal|cantilever, default = active part (else brake_pedal)",
    )


class RunConvergenceStudyArgs(BaseModel):
    mesh_sizes_mm: list[float] | None = Field(
        default=None,
        description=(
            "Optional explicit mesh sizes mm (2-4 distinct entries, coarse->fine); "
            "default ladder = 1.0x/0.7x/0.5x of the part default"
        ),
    )
    force_n: float | None = Field(
        default=None,
        description="Load in N (default 500 pedal / 100 cantilever)",
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
