# ADR-008: Remove the engine mount

Date: 2026-08-16 · Status: accepted

## Context

The engine mount (L-bracket, `companion/tools/engine_mount.py`) was one of
three demo parts alongside the brake pedal and cantilever. It added the least
demo value: its FEA is close to pure axial compression (the F07 idealization
was literally F/A), it duplicates the lattice story the pedal tells better,
and its two tools plus parameter tables rode in every system prompt and
`bind_tools` payload — a token tax on every turn for a part nobody was
demoing. The flagship roadmap part is the UAV arm (F26), which was always
planned to follow the `brake_pedal.py` generator pattern, not the mount.

Per AGENTS.md rule 7, removing tools requires an explicit decision record;
this is it (owner-approved 2026-08-16).

## Decision

Remove the engine mount entirely: module, tools (`create_engine_mount`,
`compare_mount_variants`), solve path, design-program entry, heuristic-router
branches, LangChain schema, golden JSONs, RAG doc, tests, and eval cases.
The part family becomes brake pedal + cantilever until F26 adds the UAV arm.

What is deliberately kept:

- Historical ADRs (002/003/004/007) that mention the mount — they record
  decisions as made, not the current part list.
- `brake_pedal.py`'s BCC aliasing (`bcc` → `xtruss`), which predates the
  mount and keeps old pedal prompts working.

## Consequences

- Tool count 12 → 10; two fewer specs in every system prompt and two fewer
  schemas in `bind_tools` — the token budget the UAV arm tool will spend.
- Eval cases retargeted, not just deleted: `tool_create_mount` /
  `tool_mount_metrics` / `tool_compare_mount` became pedal equivalents so
  `get_lattice_metrics` and `compare_brake_pedal_variants` keep eval
  coverage; `agent_mount_lattice` became `agent_pedal_lattice`;
  `rag_engine_mount` became `rag_pedal_design_space`; `rag_backup` now asks
  about the brake pedal.
- `tests/test_mount_heuristics.py` renamed to `test_pedal_heuristics.py`
  (it always contained pedal routing tests; the mount ones moved out).
- Run history and design programs are part-keyed, so old
  `engine_mount_runs.jsonl` / `engine_mount_program.json` files in
  `data/workspace/` are simply deleted, not migrated.
- Demo narrative tightens: cantilever (verification) → brake pedal
  (lattice + history + estimates) → UAV arm (flagship, F26).
