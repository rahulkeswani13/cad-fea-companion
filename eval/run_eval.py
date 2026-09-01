#!/usr/bin/env python3
"""Run eval cases for RAG, tools, and agent heuristics.

Additive layers (evals plan):
- deterministic trajectory checks on agent cases (always on, gating);
- rubric-based LLM judge on agent answers, opt-in via EVAL_JUDGE=1
  (advisory — verdicts recorded, never gating);
- ``requires_judge`` cases report as skipped on key-less runs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from companion.agent.graph import run_agent
from companion.config import get_settings
from companion.rag.store import ingest_docs, retrieve
from companion.tools.cad_fea import call_tool
import companion.tools.freecad_runtime as f_rt
from eval import judge
from eval import trajectory

# Enforce headless evaluation: suppress GUI popups during automated test sweeps
f_rt.open_in_freecad_gui = lambda *args, **kwargs: {"ok": True, "skipped": "eval_headless"}

JUDGE_MODEL_DEFAULT = "gemini-3.5-flash-lite"


def contains_any(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    return any(n.lower() in lower for n in needles)


def _print_row(cid: str, ok: bool, detail: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {cid}  {detail}")


def main() -> int:
    cases_path = ROOT / "eval" / "cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    ingest_docs()

    passed = 0
    failed = 0
    skipped = 0
    judge_verdicts: list[dict] = []
    rows = []
    judge_model = os.environ.get("EVAL_JUDGE_MODEL", JUDGE_MODEL_DEFAULT)

    for case in cases:
        cid = case["id"]
        ok = False
        detail = ""

        if case["type"] == "agent" and case.get("requires_judge") and not judge.judge_enabled():
            skipped += 1
            rows.append({"id": cid, "ok": True, "skipped": True, "detail": "skipped (needs judge)"})
            print(f"SKIP  {cid}  needs judge (set EVAL_JUDGE=1 with a key to grade)")
            continue

        try:
            if case["type"] == "rag":
                hits = retrieve(case["query"], k=4)
                blob = "\n".join(h["text"] for h in hits) + "\n" + "\n".join(
                    h["source"] for h in hits
                )
                ok = len(hits) >= case.get("min_citations", 1) and contains_any(
                    blob, case.get("expect_any", [])
                )
                detail = f"hits={len(hits)}"
            elif case["type"] == "tool":
                result = call_tool(case["tool"], case.get("args") or {})
                ok = bool(result.get("ok")) == bool(case.get("expect_ok", True))
                if ok and "expect_error_class" in case:
                    ok = result.get("error_class") == case["expect_error_class"]
                if ok and case.get("expect_correction"):
                    ok = bool(str(result.get("correction") or "").strip())
                if ok and "expect_validation_stage" in case:
                    ok = (result.get("validation") or {}).get("stage") == case[
                        "expect_validation_stage"
                    ]
                if ok and case.get("expect_receipt"):
                    receipt = result.get("receipt") or {}
                    ok = receipt.get("tool") == case["tool"] and isinstance(
                        receipt.get("elapsed_s"), (int, float)
                    )
                if ok and case.get("expect_fields"):
                    ok = all(
                        result.get(field) is not None
                        for field in case["expect_fields"]
                    )
                if ok and "expect_stress_approx_mpa" in case:
                    stress = float(
                        result.get("max_von_mises_mpa")
                        or result.get("full_results", {}).get("max_von_mises_mpa")
                        or 0
                    )
                    tol = float(case.get("tol_mpa", 5))
                    ok = abs(stress - float(case["expect_stress_approx_mpa"])) <= tol
                    detail = f"stress={stress}"
                elif ok and "expect_stress_any_mpa" in case:
                    # Pass if any [value, tol] pair matches — one entry per
                    # deterministic outcome path (fallback/analytical value,
                    # live coarse-mesh value when FreeCAD runs the solve).
                    stress = float(
                        result.get("max_von_mises_mpa")
                        or result.get("full_results", {}).get("max_von_mises_mpa")
                        or 0
                    )
                    ok = any(
                        abs(stress - float(value)) <= float(tol)
                        for value, tol in case["expect_stress_any_mpa"]
                    )
                    detail = f"stress={stress}"
                else:
                    detail = json.dumps(result)[:180]
            elif case["type"] == "agent":
                out = run_agent(case["message"])
                answer = out.get("answer") or ""
                tools = [t.get("name") for t in out.get("tool_results") or []]
                ok = True
                if case.get("expect_any"):
                    ok = ok and contains_any(answer, case["expect_any"])
                if case.get("min_citations"):
                    ok = ok and len(out.get("citations") or []) >= case["min_citations"]
                if case.get("expect_tools_any"):
                    ok = ok and any(t in tools for t in case["expect_tools_any"])
                detail = f"tools={tools}"
                # Deterministic trajectory checks: gating (unlike the judge).
                traj = trajectory.run_trajectory_checks(case, out.get("tool_results") or [])
                if traj:
                    ok = False
                    detail += " | " + "; ".join(traj)
                # Rubric judge: advisory — recorded, never gates.
                if judge.judge_enabled():
                    verdict = judge.judge_agent_case(
                        case,
                        answer,
                        tools,
                        get_settings().gemini_api_key,
                        judge_model,
                    )
                    judge_verdicts.append({"id": cid, **verdict})
                    grade = (
                        "PASS" if verdict.get("pass") is True
                        else "FAIL" if verdict.get("pass") is False
                        else str(verdict.get("verdict") or "?").upper()
                    )
                    detail += f" | judge={grade}"
                    rows.append({"id": cid, "ok": ok, "judge": verdict, "detail": detail})
                    _print_row(cid, ok, detail)
                    if ok:
                        passed += 1
                    else:
                        failed += 1
                    continue
            else:
                detail = f"unknown type {case['type']}"
        except Exception as exc:  # noqa: BLE001
            ok = False
            detail = f"exception: {exc}"

        rows.append({"id": cid, "ok": ok, "detail": detail})
        _print_row(cid, ok, detail)
        if ok:
            passed += 1
        else:
            failed += 1

    judge_rows = [v for v in judge_verdicts]
    tokens = {
        "input_tokens": sum((v.get("usage") or {}).get("input_tokens", 0) for v in judge_rows),
        "output_tokens": sum((v.get("usage") or {}).get("output_tokens", 0) for v in judge_rows),
    }
    summary = {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": len(cases),
        "rows": rows,
        "judge": {
            "enabled": judge.judge_enabled(),
            "model": judge_model if judge.judge_enabled() else None,
            "graded": len(judge_rows),
            "judge_passed": sum(1 for v in judge_rows if v.get("pass") is True),
            "judge_failed": sum(1 for v in judge_rows if v.get("pass") is False),
            "judge_unparsed": sum(1 for v in judge_rows if v.get("verdict") != "graded"),
            "tokens": tokens,
            "verdicts": judge_rows,
        },
    }
    out_path = ROOT / "data" / "results" / "eval_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    judge_line = ""
    if judge.judge_enabled():
        judge_line = (
            f" | judge: {summary['judge']['judge_passed']}/{len(judge_rows)} passed,"
            f" {tokens['input_tokens']}in/{tokens['output_tokens']}out tokens"
        )
    print(
        f"\nSummary: {passed}/{len(cases)} passed"
        + (f", {skipped} skipped" if skipped else "")
        + f" -> {out_path}{judge_line}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
