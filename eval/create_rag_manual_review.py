"""Create a hash-bound, per-case human-review worksheet for RAG answers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "eval" / "rag_hidden_v2.json"


class ManualReviewTemplateError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_template(
    answer_report: dict[str, Any],
    answer_report_sha256: str,
    fixture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = [
        row for row in (answer_report.get("rows") or [])
        if isinstance(row, dict) and row.get("generation_status") == "complete"
    ]
    ids = [str(row.get("id") or "") for row in rows]
    if len(rows) != 30 or any(not value for value in ids) or len(set(ids)) != 30:
        raise ManualReviewTemplateError(
            "manual review requires exactly 30 uniquely identified generated answers"
        )
    cases = {
        str(case.get("id")): case
        for case in ((fixture or {}).get("cases") or [])
        if isinstance(case, dict) and case.get("id")
    }
    if fixture is not None and set(cases) != set(ids):
        raise ManualReviewTemplateError(
            "manual review fixture case set does not match the answer report"
        )
    return {
        "schema_version": 1,
        "fixture_id": answer_report.get("fixture_id"),
        "answer_report_sha256": answer_report_sha256,
        "status": "pending",
        "reviewer_type": "human",
        "instructions": (
            "Replace every null mark after reviewing the exact answer and its evidence. "
            "Set status to complete only after all 30 rows are reviewed."
        ),
        "reviews": [
            {
                "id": row["id"],
                "critical": row.get("critical") is True,
                "query": (cases.get(row["id"]) or {}).get("query"),
                "history": (cases.get(row["id"]) or {}).get("history") or [],
                "expected_behavior": row.get("expected_behavior"),
                "expected_summary": (cases.get(row["id"]) or {}).get("expected_summary"),
                "required_facts": (cases.get(row["id"]) or {}).get("required_facts") or [],
                "numeric_expectations": (
                    (cases.get(row["id"]) or {}).get("numeric_expectations") or []
                ),
                "forbidden_claims": (
                    (cases.get(row["id"]) or {}).get("forbidden_claims") or []
                ),
                "actual_action": row.get("actual_action"),
                "answer": row.get("answer"),
                "assessment_status": (row.get("assessment") or {}).get("status"),
                "assessment": row.get("assessment") or {},
                "evidence": row.get("evidence") or [],
                "advisory_judge": row.get("semantic_evaluation") or {},
                "behavior_correct": None,
                "required_facts_present": None,
                "numeric_units_correct": None,
                "forbidden_claim_absent": None,
                "citations_entailed": None,
                "caveats_adjacent": None,
                "factual_claims": None,
                "supported_factual_claims": None,
                "critical_numeric_violations": None,
                "notes": "",
            }
            for row in rows
        ],
    }


def _quoted(text: Any) -> str:
    return "\n".join(f"> {line}" for line in str(text or "").splitlines()) or "> (none)"


def render_markdown(template: dict[str, Any]) -> str:
    """Render the worksheet inputs for human reading; JSON remains authoritative."""
    lines = [
        "# RAG hidden-v2 final-answer review packet",
        "",
        f"Answer report SHA-256: `{template['answer_report_sha256']}`",
        "",
        "For each case, compare the answer with the expected behavior, required facts, "
        "forbidden claims, numeric expectations, and the complete cited evidence. The "
        "advisory judge is a review lead, not the decision. Record final marks in the "
        "paired JSON worksheet.",
        "",
    ]
    for index, review in enumerate(template["reviews"], 1):
        lines.extend([
            f"## {index}. {review['id']}{' — critical' if review['critical'] else ''}",
            "",
            f"Expected action: `{review['expected_behavior']}` · Actual action: "
            f"`{review['actual_action']}` · Structural status: "
            f"`{review['assessment_status']}`",
            "",
            "### Question",
            "",
            _quoted(review.get("query")),
            "",
        ])
        if review.get("history"):
            lines.extend(["### Prior conversation", ""])
            for turn in review["history"]:
                lines.append(
                    f"- **{turn.get('role', 'unknown')}:** {turn.get('content', '')}"
                )
            lines.append("")
        lines.extend([
            "### Reference expectations",
            "",
            _quoted(review.get("expected_summary")),
            "",
            "Required facts:",
            *[f"- {item}" for item in review.get("required_facts") or ["(none)"]],
            "",
            "Numeric expectations:",
            *[f"- `{json.dumps(item, sort_keys=True)}`" for item in review.get("numeric_expectations") or ["(none)"]],
            "",
            "Forbidden claims:",
            *[f"- {item}" for item in review.get("forbidden_claims") or ["(none)"]],
            "",
            "### Generated answer",
            "",
            _quoted(review.get("answer")),
            "",
            "### Retrieved evidence",
            "",
        ])
        for item in review.get("evidence") or []:
            lines.extend([
                f"**{item.get('evidence_id')} · {item.get('kind')} · {item.get('source')}**",
                "",
                _quoted(item.get("content")),
                "",
            ])
        judge = review.get("advisory_judge") or {}
        lines.extend([
            "### Advisory judge",
            "",
            f"Pass: `{judge.get('pass')}` · Supported claims: "
            f"`{judge.get('supported_claims')}` / `{judge.get('factual_claims')}` · "
            f"Critical numeric violation: `{judge.get('critical_numeric_violation')}`",
            "",
            _quoted(judge.get("notes")),
            "",
            "### Human marks to enter in the JSON worksheet",
            "",
            "- [ ] Behavior/action correct",
            "- [ ] All required facts present",
            "- [ ] Numeric values and units correct",
            "- [ ] Forbidden claims absent",
            "- [ ] Every substantive claim entailed by cited evidence",
            "- [ ] Caveats adjacent to the claims they qualify",
            "- Factual claims: ___ · Supported factual claims: ___ · Critical numeric violations: ___",
            "",
        ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answer", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    answer = json.loads(args.answer.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    try:
        template = build_template(answer, _sha256(args.answer), fixture)
    except ManualReviewTemplateError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(template), encoding="utf-8")
    print(f"Created 30-case review worksheet: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
