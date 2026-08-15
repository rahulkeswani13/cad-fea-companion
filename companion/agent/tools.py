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
    open_gui: bool = Field(default=True, description="Open FreeCAD GUI after create")


class CreateEngineMountArgs(BaseModel):
    web_type: Literal["solid", "bcc", "fcc"] = Field(
        default="bcc",
        description="Web fill: solid, bcc lattice, or fcc lattice",
    )
    cell_size_mm: float = Field(default=15.0, description="Lattice cell size mm")
    strut_radius_mm: float = Field(
        default=2.2, description="Strut radius mm (>=2.2 for meshable BCC)"
    )
    open_gui: bool = Field(default=True, description="Open FreeCAD GUI after create")


class CreateCantileverArgs(BaseModel):
    length_mm: float = Field(default=100.0, description="Beam length in mm")
    width_mm: float = Field(default=20.0, description="Beam width in mm")
    height_mm: float = Field(default=5.0, description="Beam height in mm")
    open_gui: bool = Field(default=True, description="Open FreeCAD GUI after create")


class ApplyLoadArgs(BaseModel):
    force_n: float | None = Field(
        default=None,
        description="Load in newtons (default 500 pedal / 20000 mount / 100 cantilever)",
    )
    mesh_max_size_mm: float | None = Field(
        default=None,
        description="Coarse mesh size mm (default 5 pedal / 4 mount / 2.5 cantilever)",
    )
    open_gui: bool = Field(default=True, description="Open FreeCAD GUI after solve")


class EmptyArgs(BaseModel):
    pass


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
            name="create_engine_mount",
            description=(
                "Create a simplified Al engine-mount L-bracket with solid bolt flange "
                "and load pad; web_type solid|bcc|fcc lattice fill; open FreeCAD GUI."
            ),
            args_schema=CreateEngineMountArgs,
        ),
        StructuredTool.from_function(
            func=_noop,
            name="get_lattice_metrics",
            description=(
                "Return relative density, volumes, and mass for the current "
                "brake-pedal or engine-mount geometry."
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
            name="compare_mount_variants",
            description=(
                "Compare solid vs BCC vs FCC engine-mount mass, stress, deflection; "
                "recommend lightest with SF>=1.5."
            ),
            args_schema=EmptyArgs,
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
                "save results, and open the FEM document. Requires create_brake_pedal, "
                "create_engine_mount, or create_cantilever first."
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
            name="open_in_freecad",
            description="Launch FreeCAD GUI with the latest CAD/FEM document.",
            args_schema=EmptyArgs,
        ),
    ]


# Tools that open/mutate FreeCAD GUI — candidates for HITL confirm
FREECAD_MUTATING_TOOLS = frozenset(
    {
        "create_brake_pedal",
        "create_engine_mount",
        "create_cantilever",
        "apply_load_and_solve",
        "open_in_freecad",
    }
)
