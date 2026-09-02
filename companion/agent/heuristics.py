"""H6: HeuristicRouter — the offline-first tool planner, as a module.

The keyword router that plans CAD/FEA tools when no LLM is configured (or
when the LLM omits tools on a first visit) used to live inline in
``graph.py``. This module makes it a designed, testable component:
``settings.heuristic_fallback`` (default true) documents and gates the
offline mode. Behavior is identical to the extracted implementation.
"""

from __future__ import annotations

import re
from typing import Any

from companion.tools import materials as mats


class HeuristicRouter:
    """Keyword-driven one-tool-at-a-time planner (no network, deterministic)."""

    # --- orientation helpers -------------------------------------------------

    def pedal_oriented(self, message: str) -> bool:
        lower = message.lower()
        return any(
            k in lower
            for k in (
                "brake pedal",
                "brake-pedal",
                "pedal",
                "footpad",
                "pushrod",
                "clevis",
                "pivot hole",
            )
        )

    def lattice_oriented(self, message: str) -> bool:
        lower = message.lower()
        return any(
            k in lower
            for k in (
                "lattice",
                "bcc",
                "fcc",
                "xtruss",
                "x-truss",
                "x truss",
                "truss",
                "relative density",
                "bracket",
            )
        )

    def uav_oriented(self, message: str) -> bool:
        lower = message.lower()
        return any(
            k in lower
            for k in (
                "uav",
                "drone",
                "quadcopter",
                "quad-copter",
                "motor mount",
                "motor-mount",
                "motor ring",
            )
        )

    def has_cad_tool_intent(self, message: str) -> bool:
        """True when the user asked to mutate CAD/FEA, not just ask a docs question."""
        lower = message.lower()
        return any(
            k in lower
            for k in (
                "create",
                "make",
                "build",
                "rebuild",
                "generate",
                "solve",
                "apply",
                "compare",
                "which lattice",
                "which variant",
                "lightest",
                "run fea",
                "run fem",
                "static analysis",
                "open freecad",
                "launch freecad",
                "show in freecad",
                "open the latest model",
                "lattice metrics",
                "get_lattice",
                "get_max_von_mises",
            )
        )

    # --- planning ------------------------------------------------------------

    def plan_tools(self, message: str) -> list[dict[str, Any]]:
        lower = message.lower()
        calls: list[dict[str, Any]] = []

        wants_create_kw = any(
            k in lower for k in ("create", "make", "build", "generate", "rebuild")
        )
        uav = self.uav_oriented(lower)
        wants_pedal = self.pedal_oriented(lower) and wants_create_kw and not uav
        # Default lattice → brake pedal (UAV arms own their lattice routing).
        wants_lattice_default = self.lattice_oriented(lower) and wants_create_kw and not uav
        if wants_pedal or wants_lattice_default:
            args: dict[str, Any] = {}
            if "fcc" in lower:
                args["web_type"] = "fcc"
            elif (
                "solid" in lower
                and "xtruss" not in lower
                and "truss" not in lower
                and "bcc" not in lower
            ):
                args["web_type"] = "solid"
            else:
                # Default lattice fill for pedal is 2.5D X-truss (bcc aliases here).
                args["web_type"] = "xtruss"
            calls.append({"name": "create_brake_pedal", "args": args})

        # F26: UAV arm flagship part. Default web is solid (the demo baseline);
        # lattice/truss wording upgrades it to the X-truss web.
        if uav and wants_create_kw:
            args_u: dict[str, Any] = {}
            if any(k in lower for k in ("xtruss", "x-truss", "x truss", "truss", "lattice", "bcc")):
                args_u["web_type"] = "xtruss"
            elif "solid" in lower:
                args_u["web_type"] = "solid"
            calls.append({"name": "create_uav_arm", "args": args_u})

        wants_compare = any(
            k in lower
            for k in (
                "compare",
                "which lattice",
                "which variant",
                "best lattice",
                "lightest",
                "recommend",
            )
        ) and (
            self.pedal_oriented(lower)
            or self.lattice_oriented(lower)
            or "solid" in lower
            or "variant" in lower
        )
        if wants_compare:
            calls.append({"name": "compare_brake_pedal_variants", "args": {}})

        # F09: material questions. "Ti vs Al" style questions compare the table;
        # "switch to Ti" style edits go through the design program.
        _MATERIAL_HINTS = (
            "material",
            "titanium",
            "ti-6al",
            "ti6al",
            " ti ",
            " ti64",
            "7075",
            "6061",
            "pa12",
            "nylon",
            "aluminum",
            "aluminium",
            "steel",
            "alloy",
        )
        mentions_material = any(k in lower for k in _MATERIAL_HINTS)
        if mentions_material:
            mentioned = None
            for token in re.findall(r"[A-Za-z0-9-]+", lower):
                record = mats.get_material(token)
                if record:
                    mentioned = record["id"]
                    break
            wants_set_material = any(
                k in lower
                for k in ("switch", "make it", "change to", "convert", "set the material")
            )
            wants_material_compare = any(
                k in lower
                for k in ("compare", " vs ", "versus", "which material", "better", "what about")
            )
            if mentioned and wants_set_material:
                calls.append(
                    {"name": "update_design_program", "args": {"changes": {"material": mentioned}}}
                )
            elif wants_material_compare or mentioned is None:
                calls.append({"name": "compare_materials", "args": {}})

        wants_metrics = any(
            k in lower
            for k in ("lattice metrics", "mass estimate", "get_lattice", "get lattice metrics")
        )
        if wants_metrics:
            calls.append({"name": "get_lattice_metrics", "args": {}})

        wants_create = any(
            k in lower for k in ("create", "make a cantilever", "build a beam", "cantilever")
        ) and any(k in lower for k in ("create", "make", "build", "mm", "x"))
        if (
            not self.pedal_oriented(lower)
            and not self.lattice_oriented(lower)
            and not self.uav_oriented(lower)
            and (wants_create or ("cantilever" in lower and "x" in lower))
        ):
            args_c: dict[str, Any] = {}
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)",
                lower,
            )
            if m:
                args_c = {
                    "length_mm": float(m.group(1)),
                    "width_mm": float(m.group(2)),
                    "height_mm": float(m.group(3)),
                }
            if "create" in lower or "make" in lower or "build" in lower or args_c:
                calls.append({"name": "create_cantilever", "args": args_c})

        wants_convergence = any(
            k in lower
            for k in (
                "convergence",
                "converged",
                "mesh study",
                "mesh sensitivity",
                "mesh refinement",
                "refine the mesh",
                "run_convergence_study",
            )
        )
        if wants_convergence:
            args_cv: dict[str, Any] = {}
            fm_cv = re.search(r"(\d+(?:\.\d+)?)\s*n\b", lower)
            if fm_cv:
                args_cv["force_n"] = float(fm_cv.group(1))
            calls.append({"name": "run_convergence_study", "args": args_cv})

        wants_solve = any(
            k in lower
            for k in (
                "apply",
                "solve",
                "run fea",
                "run fem",
                "tip load",
                "static analysis",
                "100 n",
                "100n",
                "500 n",
                "500n",
                "20000 n",
                "20000n",
                "2000 n",
                "2000n",
                "pad load",
                "footpad",
            )
        )
        if wants_solve:
            args_s: dict[str, Any] = {}
            fm = re.search(r"(\d+(?:\.\d+)?)\s*n\b", lower)
            if fm:
                args_s["force_n"] = float(fm.group(1))
            calls.append({"name": "apply_load_and_solve", "args": args_s})

        wants_stress = any(
            k in lower
            for k in (
                "von mises",
                "max stress",
                "maximum stress",
                "under 50",
                "get_max_von_mises",
                "safety factor",
                "concentrated",
            )
        )
        if wants_stress:
            calls.append({"name": "get_max_von_mises", "args": {}})

        if any(
            k in lower
            for k in (
                "open freecad",
                "launch freecad",
                "show in freecad",
                "open the latest model",
                "open free cad",
            )
        ):
            calls.append({"name": "open_in_freecad", "args": {}})
        return calls

    @staticmethod
    def _done_tool_names(tool_results: list[dict[str, Any]]) -> set[str]:
        names: set[str] = set()
        for item in tool_results:
            result = item.get("result") or {}
            if result.get("ok") is False:
                continue
            if result.get("cancelled"):
                continue
            names.add(str(item.get("name", "")))
        return names

    def plan(
        self,
        message: str,
        cad_geometry: dict[str, Any] | None,
        cad_results: dict[str, Any] | None,
        tool_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return at most one next tool so the agent loop can observe results."""
        planned = self.plan_tools(message)
        lower = message.lower()
        if not planned and any(
            k in lower
            for k in (
                "create",
                "solve",
                "cantilever",
                "von mises",
                "lattice",
                "pedal",
                "brake",
                "bcc",
                "fcc",
                "compare",
                "uav",
                "drone",
            )
        ):
            planned = self.plan_tools(message)

        done = self._done_tool_names(tool_results)
        failed = {
            str(item.get("name"))
            for item in tool_results
            if (item.get("result") or {}).get("ok") is False
            and not (item.get("result") or {}).get("cancelled")
        }
        explicit_create = any(k in lower for k in ("create", "make", "build", "rebuild"))
        pedalist = self.pedal_oriented(lower) or self.lattice_oriented(lower)
        uavist = self.uav_oriented(lower)

        for call in planned:
            name = call["name"]
            if name == "create_brake_pedal":
                if cad_geometry and not explicit_create and name not in failed:
                    continue
                if name in done and name not in failed:
                    continue
                return [call]
            if name == "create_uav_arm":
                if cad_geometry and not explicit_create and name not in failed:
                    continue
                if name in done and name not in failed:
                    continue
                return [call]
            if name == "create_cantilever":
                if cad_geometry and not explicit_create and name not in failed:
                    continue
                if name in done and name not in failed:
                    continue
                return [call]
            if name == "apply_load_and_solve":
                created = (
                    "create_brake_pedal" in done
                    or "create_uav_arm" in done
                    or "create_cantilever" in done
                )
                if not cad_geometry and not created:
                    if uavist:
                        return [{"name": "create_uav_arm", "args": {"web_type": "solid"}}]
                    if pedalist:
                        return [{"name": "create_brake_pedal", "args": {"web_type": "xtruss"}}]
                    return [{"name": "create_cantilever", "args": {}}]
                if name in done and name not in failed and cad_results:
                    continue
                return [call]
            if name in (
                "get_lattice_metrics",
                "compare_brake_pedal_variants",
                "compare_materials",
            ):
                if name == "get_lattice_metrics" and not cad_geometry:
                    if "create_brake_pedal" not in done:
                        return [{"name": "create_brake_pedal", "args": {"web_type": "xtruss"}}]
                # compare_materials works from stored/precomputed runs — no live
                # geometry required, so it falls through without a create.
                if name in done:
                    continue
                return [call]
            if name == "update_design_program":
                created = (
                    "create_brake_pedal" in done
                    or "create_uav_arm" in done
                    or "create_cantilever" in done
                )
                if not cad_geometry and not created:
                    if uavist:
                        return [{"name": "create_uav_arm", "args": {"web_type": "solid"}}]
                    if pedalist:
                        return [{"name": "create_brake_pedal", "args": {"web_type": "xtruss"}}]
                    return [{"name": "create_cantilever", "args": {}}]
                if name in done and name not in failed:
                    continue
                return [call]
            if name == "run_convergence_study":
                created = (
                    "create_brake_pedal" in done
                    or "create_uav_arm" in done
                    or "create_cantilever" in done
                )
                if not cad_geometry and not created:
                    if uavist:
                        return [{"name": "create_uav_arm", "args": {"web_type": "solid"}}]
                    if pedalist:
                        return [{"name": "create_brake_pedal", "args": {"web_type": "xtruss"}}]
                    return [{"name": "create_cantilever", "args": {}}]
                if name in done and name not in failed:
                    continue
                return [call]
            if name == "get_max_von_mises":
                if name in done:
                    continue
                return [call]
            if name == "open_in_freecad":
                if name in done:
                    continue
                return [call]
        return []
