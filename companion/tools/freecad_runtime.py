"""FreeCAD discovery and subprocess helpers."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from companion.config import get_settings

CANDIDATE_CMDS = [
    "/Applications/FreeCAD.app/Contents/Resources/bin/FreeCADCmd",
    "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd",
    "/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd",
]

CANDIDATE_GUI = [
    "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD",
    "/Applications/FreeCAD.app/Contents/Resources/bin/FreeCAD",
    "/Applications/FreeCAD.app/Contents/Resources/bin/freecad",
]


def find_freecad_cmd() -> str | None:
    settings = get_settings()
    if settings.freecad_cmd and Path(settings.freecad_cmd).exists():
        return settings.freecad_cmd
    env = os.environ.get("FREECAD_CMD")
    if env and Path(env).exists():
        return env
    for path in CANDIDATE_CMDS:
        if Path(path).exists():
            return path
    which = shutil.which("FreeCADCmd") or shutil.which("freecadcmd")
    return which


def find_freecad_gui() -> str | None:
    for path in CANDIDATE_GUI:
        if Path(path).exists():
            return path
    which = shutil.which("FreeCAD") or shutil.which("freecad")
    return which


def _qt_cpu_feature_error(stdout: str, stderr: str) -> bool:
    blob = f"{stdout}\n{stderr}".lower()
    return "incompatible processor" in blob and (
        "neon" in blob or "crc32" in blob
    )


def _base_freecad_env() -> dict[str, str]:
    """Clean launch env so host Qt/Python paths do not collide with FreeCAD.app."""
    env = os.environ.copy()
    for key in (
        "DYLD_LIBRARY_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "PYTHONHOME",
        "PYTHONPATH",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QT_QPA_PLATFORM",
        "PREFIX",
        "LD_LIBRARY_PATH",
        "GIT_SSL_CAINFO",
        "SSL_CERT_FILE",
    ):
        env.pop(key, None)
    return env


def _gui_freecad_env() -> dict[str, str]:
    """GUI launch env: clean host vars, keep a normal display session."""
    env = _base_freecad_env()
    # Avoid inheriting Cursor/agent interpreter overrides into FreeCAD.app.
    for key in list(env):
        if key.startswith("ELECTRON_") or key.startswith("VSCODE_"):
            env.pop(key, None)
    return env


def _cli_freecad_env() -> dict[str, str]:
    env = _base_freecad_env()
    # Headless CLI; avoid GUI plugin probing where possible.
    env["QT_QPA_PLATFORM"] = "offscreen"
    return env


def run_freecad_python(script: str, timeout: int = 120) -> dict[str, Any]:
    """Execute a FreeCAD Python script via FreeCADCmd and parse JSON from stdout."""
    cmd = find_freecad_cmd()
    if not cmd:
        return {
            "ok": False,
            "error": "FreeCADCmd not found. Install FreeCAD and retry.",
            "freecad_cmd": None,
        }

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(script)
        script_path = handle.name

    proc = subprocess.Popen(
        [cmd, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_cli_freecad_env(),
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill the process group so orphaned Gmsh children are cleaned up.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait()
        return {"ok": False, "error": f"FreeCADCmd timed out after {timeout}s"}
    finally:
        Path(script_path).unlink(missing_ok=True)

    stdout = stdout or ""
    stderr = stderr or ""
    marker = "COMPANION_JSON:"
    payload: dict[str, Any] | None = None
    for line in stdout.splitlines():
        if marker in line:
            raw = line.split(marker, 1)[1].strip()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"ok": False, "error": f"Invalid JSON from FreeCAD: {raw}"}
            break

    if payload is None:
        if _qt_cpu_feature_error(stdout, stderr) or proc.returncode in (-6, 134):
            error = (
                "FreeCAD Qt aborted with an ARM CPU-feature check "
                "(neon/crc32; often return code -6). This usually means the "
                "server was started inside a restricted sandbox. Restart via "
                "./scripts/run_demo.sh in a normal terminal (not a sandboxed "
                "agent shell), or continue with the analytical FEM fallback."
            )
        else:
            error = "No COMPANION_JSON marker in FreeCAD output"
        return {
            "ok": False,
            "error": error,
            "returncode": proc.returncode,
            "stdout_tail": stdout[-2000:],
            "stderr_tail": stderr[-2000:],
            "freecad_cmd": cmd,
        }
    payload.setdefault("freecad_cmd", cmd)
    payload.setdefault("returncode", proc.returncode)
    return payload


def show_fit_macro_path() -> Path:
    return Path(__file__).resolve().parents[1] / "macros" / "show_fit.py"


def open_in_freecad_gui(fcstd_path: str | Path | None = None) -> dict[str, Any]:
    """Launch FreeCAD GUI, open a document, unhide FEM objects, fit isometric view."""
    path = Path(fcstd_path) if fcstd_path else None
    if path is not None and not path.exists():
        return {"ok": False, "error": f"Document not found: {path}"}

    env = _gui_freecad_env()
    gui = find_freecad_gui()
    macro = show_fit_macro_path()
    macro_arg = str(macro) if macro.exists() else None

    try:
        # Prefer the FreeCAD binary so we can pass the show/fit startup script.
        # `open -a` is less reliable for extra script arguments on macOS.
        if gui:
            cmd = [gui]
            if path is not None:
                cmd.append(str(path.resolve()))
            if macro_arg:
                cmd.append(macro_arg)
            subprocess.Popen(
                cmd,
                env=env,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "ok": True,
                "launched": " ".join(cmd),
                "fcstd_path": str(path) if path else None,
                "show_fit_macro": macro_arg,
            }

        if Path("/Applications/FreeCAD.app").exists():
            cmd = ["open", "-n", "-a", "FreeCAD"]
            args: list[str] = []
            if path is not None:
                args.append(str(path))
            if macro_arg:
                args.append(macro_arg)
            if args:
                cmd.extend(["--args", *args])
            subprocess.Popen(cmd, env=env, start_new_session=True)
            return {
                "ok": True,
                "launched": " ".join(cmd),
                "fcstd_path": str(path) if path else None,
                "show_fit_macro": macro_arg,
            }

        return {
            "ok": False,
            "error": "FreeCAD GUI not found. Install FreeCAD.app first.",
        }
    except OSError as exc:
        return {"ok": False, "error": f"Failed to launch FreeCAD GUI: {exc}"}
