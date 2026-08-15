#!/usr/bin/env python3
"""Run eval cases for RAG, tools, and agent heuristics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from companion.agent.graph import run_agent
from companion.rag.store import ingest_docs, retrieve
from companion.tools.cad_fea import call_tool


def contains_any(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    return any(n.lower() in lower for n in needles)


def main() -> int:
    cases_path = ROOT / "eval" / "cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    ingest_docs()

    passed = 0
    failed = 0
    rows = []

    for case in cases:
        cid = case["id"]
        ok = False
        detail = ""
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
                if ok and "expect_stress_approx_mpa" in case:
                    stress = float(
                        result.get("max_von_mises_mpa")
                        or result.get("full_results", {}).get("max_von_mises_mpa")
                        or 0
                    )
                    tol = float(case.get("tol_mpa", 5))
                    ok = abs(stress - float(case["expect_stress_approx_mpa"])) <= tol
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
            else:
                detail = f"unknown type {case['type']}"
        except Exception as exc:  # noqa: BLE001
            ok = False
            detail = f"exception: {exc}"

        rows.append({"id": cid, "ok": ok, "detail": detail})
        if ok:
            passed += 1
            print(f"PASS  {cid}  {detail}")
        else:
            failed += 1
            print(f"FAIL  {cid}  {detail}")

    summary = {"passed": passed, "failed": failed, "total": len(cases), "rows": rows}
    out_path = ROOT / "data" / "results" / "eval_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary: {passed}/{len(cases)} passed -> {out_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
