#!/usr/bin/env python3
"""Smoke-test FreeCADCmd: cantilever + brake-pedal X-truss."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from companion.tools.cad_fea import create_brake_pedal, create_cantilever
from companion.tools.freecad_runtime import find_freecad_cmd


def main() -> int:
    cmd = find_freecad_cmd()
    print(f"FreeCADCmd: {cmd or 'NOT FOUND'}")
    beam = create_cantilever(100, 20, 5, open_gui=False)
    print("cantilever:", {k: beam.get(k) for k in ("ok", "part", "warning", "fcstd_path")})
    pedal = create_brake_pedal(web_type="xtruss", open_gui=False)
    print(
        "brake_pedal:",
        {
            k: pedal.get(k)
            for k in (
                "ok",
                "part",
                "web_type",
                "relative_density",
                "mass_kg",
                "warning",
                "fcstd_path",
            )
        },
    )
    ok = bool(beam.get("ok") and pedal.get("ok"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
