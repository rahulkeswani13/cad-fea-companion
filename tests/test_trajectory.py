"""Unit tests for the deterministic trajectory checkers (evals plan phase 1)."""

from __future__ import annotations

from eval.trajectory import (
    check_max_rounds,
    check_no_noop_repeat,
    check_tool_order,
    run_trajectory_checks,
)


def _hit(name: str, args: dict | None = None) -> dict:
    return {"name": name, "args": args or {}, "result": {"ok": True}}


def _miss(name: str, args: dict | None = None) -> dict:
    return {"name": name, "args": args or {}, "result": {"ok": False}}


def test_tool_order_passes_and_flags_violations():
    good = [_hit("create_uav_arm"), _hit("apply_load_and_solve")]
    assert check_tool_order(good, "create_uav_arm", "apply_load_and_solve") == []
    # solve ran without any create
    bad_missing = [_hit("apply_load_and_solve")]
    assert check_tool_order(bad_missing, "create_uav_arm", "apply_load_and_solve")
    # create ran after the solve
    bad_order = [_hit("apply_load_and_solve"), _hit("create_uav_arm")]
    assert check_tool_order(bad_order, "create_uav_arm", "apply_load_and_solve")
    # `after` never ran — vacuous, not a violation
    assert check_tool_order([_hit("create_uav_arm")], "create_uav_arm", "apply_load_and_solve") == []


def test_tool_order_ignores_failed_calls():
    # a failed create before the solve does not satisfy the ordering
    results = [_miss("create_uav_arm"), _hit("apply_load_and_solve")]
    assert check_tool_order(results, "create_uav_arm", "apply_load_and_solve")


def test_no_noop_repeat_flags_identical_successive_calls():
    assert check_no_noop_repeat([_hit("query_results")]) == []
    assert check_no_noop_repeat([_hit("query_results"), _miss("query_results")]) == []
    twice = [_hit("query_results", {"run_id": "r1"}), _hit("query_results", {"run_id": "r1"})]
    assert check_no_noop_repeat(twice) == [
        "noop repeat: 'query_results' called twice with identical args"
    ]
    # different args are legitimate re-use, not a noop repeat
    varied = [
        _hit("query_results", {"run_id": "r1"}),
        _hit("query_results", {"run_id": "r2"}),
    ]
    assert check_no_noop_repeat(varied) == []


def test_max_rounds_flags_overrun():
    assert check_max_rounds([_hit("a"), _hit("b")], 6) == []
    overrun = [_hit(str(i)) for i in range(7)]
    assert check_max_rounds(overrun, 6) == [
        "max rounds: 7 successful tool calls exceeds limit 6"
    ]


def test_run_trajectory_checks_reads_case_fields():
    case = {
        "expect_tool_order": {"before": "create_uav_arm", "after": "apply_load_and_solve"},
        "expect_no_repeat_tools": True,
        "expect_max_rounds": 6,
    }
    clean = [_hit("create_uav_arm"), _hit("apply_load_and_solve", {"force_n": 120})]
    assert run_trajectory_checks(case, clean) == []
    dirty = [_hit("apply_load_and_solve", {"force_n": 120})]
    failures = run_trajectory_checks(case, dirty)
    assert len(failures) == 1  # ordering violated; repeats/rounds fine
    assert "tool order" in failures[0]
    # empty case fields -> no checks
    assert run_trajectory_checks({}, dirty) == []
