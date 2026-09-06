# Failure repair guidance

Tool failures are returned as compact, actionable outcomes. A dispatched tool
result always carries a `receipt`; a failure carries one `error`, an
`error_class`, and one concrete `correction`. Long tracebacks and stdout/stderr
tails are written to the workspace debug log and referenced by `debug_ref`.
The correction is a next step, not proof that a retry will succeed.

## Current failure classes

| `error_class` | Meaning | One correction exposed by the tool |
|---|---|---|
| `bad_params` | Argument or design-program value is invalid | Fix the reported value or range and retry the same tool. |
| `unknown_tool` | Requested tool is not registered | Use a tool listed in the available tool specification. |
| `no_geometry` | No active or persisted geometry is available | Create the relevant part, then retry. |
| `no_results` | No solve result or requested run is available | Run `apply_load_and_solve`, or list stored runs, then retry. |
| `freecad_missing` | FreeCAD is unavailable | Install FreeCAD or set `FREECAD_CMD`; an analytical/precomputed fallback may still be usable for ordinary solves. |
| `freecad_timeout` | FreeCAD or meshing exceeded its timeout | Retry with a coarser mesh, or accept the explicitly labeled fallback. |
| `freecad_crash` | FreeCAD exited without a usable payload | Retry once with defaults; if it repeats, inspect the debug log or use the labeled fallback. |
| `mesh_failed` | Meshing failed | Increase lattice strut size and use a coarser mesh. |
| `solve_failed` | CalculiX did not produce usable results | Retry once with defaults; if it repeats, use the labeled fallback. |
| `geometry_invalid` | B-Rep validation failed before meshing | Retry with valid, lattice-friendly geometry and inspect the validation details. |
| `unsupported_setup` | The requested workflow cannot produce the needed evidence | Switch to a live-solve setup and retry. For convergence, use `solid` or `xtruss` with FreeCAD available. |
| `user_cancelled` | The operator rejected the FreeCAD confirmation gate | Re-run the request and approve the confirmation prompt. |
| `internal_error` | Unexpected tool failure | Retry once; if it repeats, inspect `data/workspace/logs/tool_debug.log`. |

The agent can observe `ok: false` and decide whether to correct parameters,
create missing geometry, retry, or stop. There is no guarantee of an automatic
retry, and a correction does not override the human confirmation gate. Failed
design-program rebuilds preserve the accepted revision; see
`docs/reference/design_programs.md`.

Source and applicability: failure classes and corrections are the current
`companion/tools/outcome.py` envelope plus the convergence and design-program
callers (ADR-002, ADR-003, ADR-009). This page documents operational guidance;
it does not certify geometry, solver output, or part safety.
