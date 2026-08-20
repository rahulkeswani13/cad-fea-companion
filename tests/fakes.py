"""Test doubles: scripted LLM turns and stub CAD/FEA tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from companion.llm.providers import AgentTurn, LLMProvider, ToolCallSpec
from companion.tools import brake_pedal as bp


@dataclass
class ScriptedLLMProvider(LLMProvider):
    """Returns predetermined AgentTurns in order (then repeats the last)."""

    turns: list[AgentTurn]
    calls: list[list[Any]] = field(default_factory=list)
    _idx: int = 0

    def complete(self, system: str, user: str) -> str:
        turn = self.complete_messages([])
        return turn.content

    def complete_messages(
        self,
        messages: list[Any],
        tools: list[Any] | None = None,
    ) -> AgentTurn:
        self.calls.append(list(messages))
        if not self.turns:
            return AgentTurn(content="(no scripted turns)")
        if self._idx < len(self.turns):
            turn = self.turns[self._idx]
            self._idx += 1
            return turn
        return self.turns[-1]


def tc(name: str, args: dict[str, Any] | None = None) -> ToolCallSpec:
    return ToolCallSpec(name=name, args=args or {})


class StubTools:
    """In-memory CAD/FEA tool stub with controllable failures."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.geometry: dict[str, Any] | None = None
        self.results: dict[str, Any] | None = None
        self.fail_create_times: int = 0
        self._create_attempts: int = 0

    def __call__(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(args or {})
        self.calls.append((name, args))
        if name == "create_brake_pedal":
            self._create_attempts += 1
            if self._create_attempts <= self.fail_create_times:
                return {"ok": False, "error": "stub create failure"}
            wt = bp.normalize_web_type(str(args.get("web_type", "xtruss")))
            vols = bp.estimate_part_volume_mm3(wt)
            self.geometry = {
                "ok": True,
                "part": "brake_pedal",
                "web_type": wt,
                "cell_size_mm": float(args.get("cell_size_mm", bp.DEFAULT_CELL_SIZE_MM)),
                "strut_radius_mm": float(
                    args.get("strut_radius_mm", bp.DEFAULT_STRUT_RADIUS_MM)
                ),
                **vols,
            }
            return dict(self.geometry)
        if name == "create_cantilever":
            self._create_attempts += 1
            if self._create_attempts <= self.fail_create_times:
                return {"ok": False, "error": "stub create failure"}
            self.geometry = {
                "part": "cantilever",
                "length_mm": float(args.get("length_mm", 100)),
                "width_mm": float(args.get("width_mm", 20)),
                "height_mm": float(args.get("height_mm", 5)),
                "ok": True,
            }
            return {"ok": True, **self.geometry}
        if name == "apply_load_and_solve":
            if not self.geometry:
                return {
                    "ok": False,
                    "error": (
                        "No geometry. Call create_brake_pedal "
                        "or create_cantilever first."
                    ),
                }
            if self.geometry.get("part") == "brake_pedal":
                force = float(args.get("force_n", bp.DEFAULT_FORCE_N))
                fea = bp.fallback_fea_result(
                    str(self.geometry.get("web_type", "xtruss")), force, self.geometry
                )
                self.results = fea
                return dict(fea)
            if self.geometry.get("part") == "uav_arm":
                force = float(args.get("force_n", 120))
                is_truss = self.geometry.get("web_type") == "xtruss"
                stress = 95.0 if is_truss else 44.6
                self.results = {
                    "ok": True,
                    "part": "uav_arm",
                    "max_von_mises_mpa": stress,
                    "force_n": force,
                    "hotspot": {"x": 12.4, "y": -8.1, "z": 5.0},
                }
                return dict(self.results)
            force = float(args.get("force_n", 100))
            L = self.geometry["length_mm"]
            b = self.geometry["width_mm"]
            h = self.geometry["height_mm"]
            stress = (6.0 * force * L) / (b * h * h)
            self.results = {
                "ok": True,
                "part": "cantilever",
                "max_von_mises_mpa": round(stress, 4),
                "force_n": force,
                "analytical_reference_mpa": round(stress, 4),
            }
            return dict(self.results)
        if name == "get_lattice_metrics":
            if not self.geometry or self.geometry.get("part") != "brake_pedal":
                return {"ok": False, "error": "No lattice geometry."}
            return {"ok": True, **self.geometry}
        if name == "compare_brake_pedal_variants":
            variants = []
            for wt in ("solid", "xtruss", "fcc"):
                fea = bp.fallback_fea_result(wt, bp.DEFAULT_FORCE_N)
                variants.append(
                    {
                        "web_type": wt,
                        "mass_kg": fea["mass_kg"],
                        "relative_density": fea["relative_density"],
                        "max_von_mises_mpa": fea["max_von_mises_mpa"],
                        "pad_deflection_mm": fea["pad_deflection_mm"],
                        "safety_factor_vs_yield": fea["safety_factor_vs_yield"],
                    }
                )
            ok_sf = [v for v in variants if (v.get("safety_factor_vs_yield") or 0) >= 1.5]
            rec = min(ok_sf, key=lambda v: float(v["mass_kg"]))
            return {"ok": True, "part": "brake_pedal", "variants": variants, "recommendation": rec}
        if name == "get_max_von_mises":
            if not self.results:
                return {"ok": False, "error": "No results yet."}
            return {
                "ok": True,
                "max_von_mises_mpa": self.results["max_von_mises_mpa"],
            }
        if name == "create_uav_arm":
            self._create_attempts += 1
            if self._create_attempts <= self.fail_create_times:
                return {"ok": False, "error": "stub create failure"}
            wt = str(args.get("web_type") or args.get("variant") or "solid")
            rad = float(args.get("strut_radius_mm", 1.8))
            if rad < 1.5 and wt == "xtruss":
                return {"ok": False, "error": f"strut_radius_mm must be in [1.5, 4.0], got {rad}", "error_class": "bad_params"}
            length = float(args.get("arm_length_mm", 180.0))
            mass_kg = 0.157 if wt == "solid" else (
                0.130 if length <= 180.0 else round(0.130 * (length / 180.0), 3)
            )
            self.geometry = {
                "ok": True,
                "part": "uav_arm",
                "web_type": wt,
                "arm_length_mm": length,
                "cell_size_mm": float(args.get("cell_size_mm", 12.0)),
                "strut_radius_mm": rad,
                "mass_kg": mass_kg,
                "step_path": f"/tmp/uav_arm_{wt}.step",
                "stl_path": f"/tmp/uav_arm_{wt}.stl",
            }
            return dict(self.geometry)
        if name == "update_design_program":
            if not self.geometry:
                return {"ok": False, "error": "No active geometry to update."}
            changes = args.get("changes") or {}
            dry_run = bool(args.get("dry_run", False))
            if "strut_radius_mm" in changes and float(changes["strut_radius_mm"]) < 1.5 and self.geometry.get("web_type") == "xtruss":
                return {"ok": False, "error": f"Preflight rejected: strut_radius_mm {changes['strut_radius_mm']} < min 1.5", "error_class": "bad_params"}
            if "cell_size_mm" in changes and float(changes["cell_size_mm"]) < 5.0:
                return {"ok": False, "error": f"Preflight rejected: cell_size_mm {changes['cell_size_mm']} < min 5.0", "error_class": "bad_params"}
            if "material" in changes:
                mat = str(changes["material"]).lower()
                if mat in ("vibranium-x", "unknown"):
                    return {"ok": False, "error": f"Unknown material '{mat}'. Supported: al6061t6, al7075t6, ti6al4v, pa12, steel", "error_class": "bad_params"}
                self.geometry["material"] = mat
            if dry_run:
                return {"ok": True, "dry_run": True, "changed": True, "proposed_hash": "a1b2c3d4"}
            # Check for no-op
            is_noop = True
            for k, v in changes.items():
                if self.geometry.get(k) != v:
                    is_noop = False
                    self.geometry[k] = v
            if is_noop and changes:
                return {"ok": True, "changed": False, "message": "No-op change: parameters already match active program."}
            if self.geometry.get("part") == "uav_arm":
                web = changes.get("web_type") or changes.get("variant")
                if web == "xtruss":
                    self.geometry["mass_kg"] = 0.130
                elif "arm_length_mm" in changes:
                    self.geometry["mass_kg"] = round(
                        0.130 * (float(changes["arm_length_mm"]) / 180.0), 3
                    )
            return {"ok": True, "changed": True, "rev": 2, "geometry": dict(self.geometry)}
        if name == "compare_materials":
            base_mass = float(self.geometry.get("mass_kg", 0.25) if self.geometry else 0.25)
            rows = [
                {"material": "al6061t6", "mass_kg": base_mass, "max_stress_mpa": 24.6, "sf": 11.2},
                {"material": "al7075t6", "mass_kg": base_mass, "max_stress_mpa": 24.6, "sf": 20.4},
                {"material": "ti6al4v", "mass_kg": round(base_mass * 1.63, 3), "max_stress_mpa": 24.6, "sf": 35.8},
                {"material": "pa12", "mass_kg": round(base_mass * 0.37, 3), "max_stress_mpa": 24.6, "sf": 1.95, "caveat": "NOT VERIFIED (large deflection / non-linear)"},
            ]
            return {"ok": True, "table": rows, "recommendation": "al7075t6"}
        if name == "run_convergence_study":
            if self.geometry and self.geometry.get("web_type") == "fcc":
                return {"ok": False, "error": "Refused: FCC pedal uses precomputed demo KPIs that do not vary with mesh size. Live solves required.", "error_class": "unsupported"}
            custom_sizes = args.get("mesh_sizes_mm") or [5.0, 3.5, 2.5]
            steps = []
            for s in custom_sizes:
                steps.append({"mesh_size_mm": float(s), "max_von_mises_mpa": round(118.0 + (5.0 - float(s)) * 1.0, 2), "tip_deflection_mm": round(1.62 + (5.0 - float(s)) * 0.03, 3)})
            return {"ok": True, "steps": steps, "recommended_mesh_mm": custom_sizes[-1], "asymptotic_delta_pct": 2.8}
        if name == "validate_cad_geometry":
            return {"ok": True, "is_valid": True, "is_watertight": True, "volume_mm3": 58000.0, "bbox": {"xmin": 0, "xmax": 180, "ymin": -15, "ymax": 15, "zmin": -10, "zmax": 10}}
        if name == "open_in_freecad":
            return {"ok": True, "opened": True}
        return {"ok": False, "error": f"Unknown tool: {name}"}

    @property
    def names(self) -> list[str]:
        return [n for n, _ in self.calls]
