Contributor guide for humans and AI agents; see `docs/adr/` for decisions.

# Agent Instructions for cad-fea-companion

Rules for coding agents (and humans) working in this repository. Applies alongside
`docs/PLAN.md` (roadmap) and `docs/adr/` (decision records).

## Goals

1. Prefer **additive** change: extend behavior without breaking existing callers.
2. Small, coherent, merge-ready diffs — one logical change at a time.
3. Never remove public surface area or change tool contracts without an ADR.

## Working rules

1. **Additive-first.** Add new functions/tools/params; keep existing signatures, defaults,
   tool names, and result shapes working. Prefer optional parameters, wrappers, and feature
   flags over rewriting call sites. Deprecate + dual-path over hard cuts.
2. **Tool results go through the outcome envelope** (`companion/tools/outcome.py`, F02):
   compact payloads, one error + one concrete correction, no raw tracebacks in LLM context.
3. **Solver honesty.** Any answer derived from a solve or surrogate must state its method
   (calculix / surrogate / analytical), mesh size when applicable, and what was *not*
   verified. See the verification-scope pattern in `docs/PLAN.md` cross-cutting rules.
4. **Every feature ships with:** unit tests in `tests/`, eval cases in `eval/cases.json`,
   a talking-script section in `demo/Features.md` (Pitch · Script · Tests · Evals ·
   Demo prompts · Likely interview questions), and an ADR entry in `docs/adr/`
   when a decision was made.
5. **Design programs are the source of truth** for parametric parts; generated geometry is
   derived. Failed rebuilds must never clobber the accepted revision.
6. Match existing style (`companion/tools/*` generator pattern, `COMPANION_JSON` sentinel
   protocol in `run_freecad_python`); do not reformat unrelated code.
7. Requires explicit approval (via ADR) before: removing/renaming tools or parameters,
   changing tool JSON schemas or wire formats, changing `.env` keys or defaults, or touching
   release/packaging.

## Verification before merging

1. `.venv/bin/python -m pytest tests/ -q` passes.
2. `.venv/bin/python eval/run_eval.py` passes (add cases for new behavior).
3. If FreeCAD is available: `scripts/smoke_freecad.py` passes.
4. No secrets or machine-specific paths committed.
