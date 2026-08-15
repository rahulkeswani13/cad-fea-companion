"""Test doubles: scripted LLM turns and stub CAD/FEA tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from companion.llm.providers import AgentTurn, LLMProvider, ToolCallSpec
from companion.tools import brake_pedal as bp
from companion.tools import engine_mount as em


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
        if name == "create_engine_mount":
            self._create_attempts += 1
            if self._create_attempts <= self.fail_create_times:
                return {"ok": False, "error": "stub create failure"}
            wt = str(args.get("web_type", "bcc"))
            vols = em.estimate_part_volume_mm3(wt)
            self.geometry = {
                "ok": True,
                "part": "engine_mount",
                "web_type": wt,
                "cell_size_mm": float(args.get("cell_size_mm", em.DEFAULT_CELL_SIZE_MM)),
                "strut_radius_mm": float(
                    args.get("strut_radius_mm", em.DEFAULT_STRUT_RADIUS_MM)
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
                        "No geometry. Call create_brake_pedal, create_engine_mount, "
                        "or create_cantilever first."
                    ),
                }
            if self.geometry.get("part") == "brake_pedal":
                force = float(args.get("force_n", bp.DEFAULT_FORCE_N))
                fea = bp.fallback_fea_result(
                    str(self.geometry.get("web_type", "bcc")), force, self.geometry
                )
                self.results = fea
                return dict(fea)
            if self.geometry.get("part") == "engine_mount":
                force = float(args.get("force_n", em.DEFAULT_FORCE_N))
                fea = em.fallback_fea_result(
                    str(self.geometry.get("web_type", "bcc")), force, self.geometry
                )
                self.results = fea
                return dict(fea)
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
            if not self.geometry or self.geometry.get("part") not in (
                "engine_mount",
                "brake_pedal",
            ):
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
        if name == "compare_mount_variants":
            variants = []
            for wt in ("solid", "bcc", "fcc"):
                fea = em.fallback_fea_result(wt, em.DEFAULT_FORCE_N)
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
            return {"ok": True, "variants": variants, "recommendation": rec}
        if name == "get_max_von_mises":
            if not self.results:
                return {"ok": False, "error": "No results yet."}
            return {
                "ok": True,
                "max_von_mises_mpa": self.results["max_von_mises_mpa"],
            }
        if name == "open_in_freecad":
            return {"ok": True, "opened": True}
        return {"ok": False, "error": f"Unknown tool: {name}"}

    @property
    def names(self) -> list[str]:
        return [n for n, _ in self.calls]
