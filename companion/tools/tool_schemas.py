"""H3 canonical tool schemas: one pydantic source of truth.

Every tool's argument model, its enforced numeric ranges, and the generated
``TOOL_SPECS`` JSON schemas derive from the models in this module:

- ``agent/tools.py`` re-exports the models for the LangChain ``bind_tools``
  path (public API unchanged);
- ``cad_fea.TOOL_SPECS`` is generated from ``TOOL_REGISTRY`` (no hand-written
  parameter prose to drift);
- ``design_program.PARAM_SPECS`` is a derived view of the same models' ``ge``
  /``le`` constraints, so program floors and boundary validation cannot
  disagree;
- ``cad_fea.call_tool`` validates args against the models *before* dispatch
  (ADR-004 philosophy: hard-reject out-of-range values, never clamp).

This module must stay dependency-free (pydantic only) — both the agent
package and the tools package import it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class CreateBrakePedalArgs(BaseModel):
    web_type: Literal["solid", "xtruss", "fcc"] = Field(
        default="xtruss",
        description="Web fill: solid, 2.5D X-truss, or fcc lattice",
    )
    cell_size_mm: float = Field(
        default=15.0, ge=5.0, le=40.0, description="Lattice cell size mm (5-40)"
    )
    strut_radius_mm: float = Field(
        default=2.5,
        ge=1.0,
        le=5.0,
        description="X-truss strut thickness mm (or FCC strut radius), 1-5",
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
    arm_length_mm: float = Field(
        default=180.0, ge=120.0, le=320.0, description="Arm length mm (120-320)"
    )
    cell_size_mm: float = Field(
        default=12.0, ge=6.0, le=30.0, description="Lattice cell size mm (6-30)"
    )
    strut_radius_mm: float = Field(
        default=1.8,
        ge=1.5,
        le=4.0,
        description="X-truss strut radius mm, 1.5 (meshable minimum) - 4",
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
    length_mm: float = Field(
        default=100.0, ge=10.0, le=500.0, description="Beam length mm (10-500)"
    )
    width_mm: float = Field(
        default=20.0, ge=2.0, le=100.0, description="Beam width mm (2-100)"
    )
    height_mm: float = Field(
        default=5.0, ge=1.0, le=50.0, description="Beam height mm (1-50)"
    )
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


class GetDesignProgramArgs(BaseModel):
    part: str | None = Field(
        default=None,
        description="brake_pedal|cantilever|uav_arm, default = active part",
    )


class UpdateDesignProgramArgs(BaseModel):
    part: str | None = Field(
        default=None,
        description="brake_pedal|cantilever|uav_arm, default = active part",
    )
    changes: dict[str, Any] | None = Field(
        default=None,
        description=(
            "object of param -> value, e.g. {\"cell_size_mm\": 12}; editable: "
            "web_type, cell_size_mm [5,40], strut_radius_mm [1,5], material "
            "(al6061t6|al7075t6|ti6al4v|pa12|steel; aliases like 'ti', "
            "'7075', 'nylon' accepted) for lattice parts; arm_length_mm "
            "[120,320], cell_size_mm [6,30], strut_radius_mm [1.5,4] for "
            "the uav_arm; or length_mm [10,500], width_mm [2,100], "
            "height_mm [1,50], material for the cantilever"
        ),
    )
    dry_run: bool = Field(
        default=False,
        description="bool, default false — preflight + hash preview only, no rebuild",
    )
    open_gui: bool = Field(default=False, description="bool, default false")


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


@dataclass(frozen=True)
class ToolSchemaEntry:
    """One tool's prompt-facing description plus its canonical args model."""

    name: str
    description: str
    args_model: type[BaseModel]


TOOL_REGISTRY: list[ToolSchemaEntry] = [
    ToolSchemaEntry(
        name="create_brake_pedal",
        description=(
            "Create a brake-pedal lattice bracket (pivot + clevis rings + footpad) "
            "with web_type solid|xtruss|fcc lattice fill, export STEP/STL, open FreeCAD GUI. "
            "Material defaults to Al 6061-T6."
        ),
        args_model=CreateBrakePedalArgs,
    ),
    ToolSchemaEntry(
        name="create_uav_arm",
        description=(
            "Create the flagship UAV arm (root clamp boss + tapered arm + tip "
            "motor-mount ring), web_type solid|xtruss (chord rails + exposed "
            "X-truss web), export STEP/STL, open FreeCAD GUI. Demo load case: "
            "120 N tip thrust at the motor ring. Material defaults to Al 6061-T6."
        ),
        args_model=CreateUavArmArgs,
    ),
    ToolSchemaEntry(
        name="get_lattice_metrics",
        description=(
            "Return relative density, volumes, and mass estimate for the current "
            "brake-pedal geometry."
        ),
        args_model=EmptyArgs,
    ),
    ToolSchemaEntry(
        name="compare_brake_pedal_variants",
        description=(
            "Compare solid vs X-truss vs FCC brake-pedal mass, relative density, "
            "max von Mises, pad deflection; recommend lightest with SF>=1.5 "
            "against the program material's yield."
        ),
        args_model=EmptyArgs,
    ),
    ToolSchemaEntry(
        name="compare_materials",
        description=(
            "F09 material comparison for a part: rows for every table material "
            "(Al 6061-T6, Al 7075-T6, Ti-6Al-4V, PA12, Steel-Generic) with mass, "
            "max von Mises, safety factor vs that material's yield, and scaled "
            "deflection, ranked by lightest at SF>=1.5. Scales the best available "
            "base run (session -> run history -> precomputed; labeled per row) "
            "linear-elastically; PA12 deflection is flagged not verified. Every "
            "row carries citation sources."
        ),
        args_model=CompareMaterialsArgs,
    ),
    ToolSchemaEntry(
        name="get_design_program",
        description=(
            "Return the persisted design program (source of truth) for a part: "
            "editable params, read-only fixed constants, revision number, and "
            "params hash. Defaults to the active part; with no active part, "
            "lists the programs on disk."
        ),
        args_model=GetDesignProgramArgs,
    ),
    ToolSchemaEntry(
        name="update_design_program",
        description=(
            "Edit the design program and rebuild the part in one step "
            "(e.g. 'set cell size to 12' without recreating): merges changes "
            "over current params, range-preflights (hard reject, never clamps), "
            "rebuilds geometry, commits the new revision on success. A failed "
            "rebuild preserves the accepted revision; a no-op change does not "
            "rebuild or bump the revision."
        ),
        args_model=UpdateDesignProgramArgs,
    ),
    ToolSchemaEntry(
        name="create_cantilever",
        description=(
            "Create a rectangular cantilever beam (mm), export STEP/STL, "
            "and open the model in the FreeCAD GUI. Material defaults to "
            "Steel-Generic."
        ),
        args_model=CreateCantileverArgs,
    ),
    ToolSchemaEntry(
        name="apply_load_and_solve",
        description=(
            "Apply load (N), mesh with Gmsh, solve with CalculiX inside FreeCAD "
            "(brake-pedal footpad, UAV-arm motor ring, or cantilever tip), save "
            "results, open GUI. Requires create_brake_pedal, create_uav_arm, or "
            "create_cantilever first."
        ),
        args_model=ApplyLoadArgs,
    ),
    ToolSchemaEntry(
        name="get_max_von_mises",
        description="Return max von Mises stress (MPa) from the latest solve.",
        args_model=EmptyArgs,
    ),
    ToolSchemaEntry(
        name="query_results",
        description=(
            "Query the stored per-run solve history: latest run in full (mass, "
            "max von Mises + its location, deflection, mesh size, method flag, "
            "expected-vs-actual divergence) plus a compact list of recent runs. "
            "'Where is stress concentrated' = max_vm_location_mm of the latest run."
        ),
        args_model=QueryResultsArgs,
    ),
    ToolSchemaEntry(
        name="run_convergence_study",
        description=(
            "Mesh convergence study for the active part: 2-3 live CalculiX "
            "solves at refining mesh sizes (default ladder = 1.0x/0.7x/0.5x "
            "of the part default, e.g. pedal 5/3.5/2.5 mm), then a "
            "recommended mesh size = the coarsest mesh within 5% of the "
            "finest max von Mises. Synchronous and headless; expect roughly "
            "the cost of 2-3 apply_load_and_solve calls. Refuses setups "
            "without live solves (fcc pedal precomputed KPIs, FreeCAD absent)."
        ),
        args_model=RunConvergenceStudyArgs,
    ),
    ToolSchemaEntry(
        name="open_in_freecad",
        description="Launch FreeCAD GUI with the latest CAD/FEM document.",
        args_model=EmptyArgs,
    ),
]

_TOOL_REGISTRY_BY_NAME: dict[str, ToolSchemaEntry] = {
    entry.name: entry for entry in TOOL_REGISTRY
}


def _json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Stable JSON schema for a tool's args (top-level title dropped)."""
    schema = model.model_json_schema()
    schema.pop("title", None)
    return schema


def build_tool_specs() -> list[dict[str, Any]]:
    """Generate the TOOL_SPECS wire format from the canonical models."""
    return [
        {
            "name": entry.name,
            "description": entry.description,
            "parameters": _json_schema(entry.args_model),
        }
        for entry in TOOL_REGISTRY
    ]


def validate_tool_args(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Boundary-validate tool args against the canonical model.

    Returns a ``bad_params`` failure payload (envelope adds correction +
    receipt) or None when the args pass — or the tool is not registered
    (unknown-tool handling lives at dispatch, H8).
    """
    entry = _TOOL_REGISTRY_BY_NAME.get(name)
    if entry is None:
        return None
    try:
        entry.args_model.model_validate(args or {})
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']) or 'args'}: {err['msg']}"
            for err in exc.errors()
        )
        return {
            "ok": False,
            "error": f"{name} rejected invalid arguments: {details}",
            "error_class": "bad_params",
        }
    return None


def _field_range(model: type[BaseModel], field: str) -> tuple[float, float]:
    """Read a model field's (ge, le) constraint pair."""
    ge: float | None = None
    le: float | None = None
    for meta in model.model_fields[field].metadata:
        value = getattr(meta, "ge", None)
        if value is not None:
            ge = float(value)
        value = getattr(meta, "le", None)
        if value is not None:
            le = float(value)
    if ge is None or le is None:
        raise ValueError(f"{model.__name__}.{field} must declare both ge and le")
    return (ge, le)


def numeric_param_ranges() -> dict[str, dict[str, tuple[float, float]]]:
    """Program floors per part, derived from the same models that gate calls."""
    return {
        "brake_pedal": {
            "cell_size_mm": _field_range(CreateBrakePedalArgs, "cell_size_mm"),
            "strut_radius_mm": _field_range(CreateBrakePedalArgs, "strut_radius_mm"),
        },
        "cantilever": {
            "length_mm": _field_range(CreateCantileverArgs, "length_mm"),
            "width_mm": _field_range(CreateCantileverArgs, "width_mm"),
            "height_mm": _field_range(CreateCantileverArgs, "height_mm"),
        },
        "uav_arm": {
            "arm_length_mm": _field_range(CreateUavArmArgs, "arm_length_mm"),
            "cell_size_mm": _field_range(CreateUavArmArgs, "cell_size_mm"),
            "strut_radius_mm": _field_range(CreateUavArmArgs, "strut_radius_mm"),
        },
    }
