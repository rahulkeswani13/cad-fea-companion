"""Regression: the eval harness's headless GUI patch must reach every importer.

cad_fea binds ``open_in_freecad_gui`` by value at import time, so patching only
``freecad_runtime`` is a no-op — a judge-enabled eval once launched a real
FreeCAD GUI through exactly this hole. These tests pin the rebind.
"""

from __future__ import annotations

import companion.tools.cad_fea as cad_fea
import companion.tools.freecad_runtime as f_rt
from eval import run_eval


def test_headless_patch_rebinds_every_importer():
    assert f_rt.open_in_freecad_gui is run_eval._headless_open_gui
    # cad_fea's by-value import must be rebound too, or the patch is a no-op
    assert cad_fea.open_in_freecad_gui is run_eval._headless_open_gui


def test_headless_stub_reports_skip_without_launching():
    assert run_eval._headless_open_gui("data/workspace/cantilever.FCStd") == {
        "ok": True,
        "skipped": "eval_headless",
    }
