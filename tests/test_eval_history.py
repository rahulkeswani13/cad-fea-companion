"""H5: eval history entries, delta computation, JSONL round-trip."""

from __future__ import annotations

import json

from eval.history import (
    append_history_entry,
    compute_delta,
    corpus_drifted,
    format_delta,
    last_history_entry,
    summarize_for_history,
)


def _summary(passed=10, failed=2, skipped=1, judge=None):
    base = {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": passed + failed + skipped,
        "judge": judge or {"enabled": False, "graded": 0, "judge_passed": 0, "judge_failed": 0},
    }
    return base


def test_summarize_extracts_counts_and_timestamp():
    entry = summarize_for_history(_summary(judge={"enabled": True, "graded": 5, "judge_passed": 4, "judge_failed": 1}))
    assert entry["passed"] == 10
    assert entry["failed"] == 2
    assert entry["total"] == 13
    assert entry["judge_graded"] == 5
    assert entry["judge_passed"] == 4
    assert "ts" in entry and "T" in entry["ts"]
    assert "rows" not in entry and "judge" not in entry  # compact only


def test_compute_delta_and_first_run_none():
    prev = summarize_for_history(_summary(passed=8, failed=4, skipped=1))
    cur = summarize_for_history(_summary(passed=10, failed=2, skipped=1))
    delta = compute_delta(prev, cur)
    assert delta["passed"] == 2
    assert delta["failed"] == -2
    assert delta["total"] == 0
    assert compute_delta(None, cur) is None


def test_compute_delta_tolerates_missing_keys():
    delta = compute_delta({"passed": 3}, {"passed": 3, "failed": 1})
    assert delta["passed"] == 0
    assert delta["failed"] == 1
    assert delta["judge_graded"] == 0


def test_format_delta_omits_zeroes():
    assert format_delta({"passed": 2, "failed": -2, "total": 0}) == "passed +2, failed -2"
    assert format_delta({"passed": 0, "failed": 0}) == ""
    assert format_delta(None) == ""


def test_jsonl_roundtrip_and_corrupt_tail(tmp_path):
    path = tmp_path / "eval_history.jsonl"
    assert last_history_entry(path) is None
    first = summarize_for_history(_summary(passed=8))
    second = summarize_for_history(_summary(passed=10))
    append_history_entry(path, first)
    append_history_entry(path, second)
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["passed"] == 8
    assert last_history_entry(path)["passed"] == 10
    # Corrupt last line is skipped, previous entry still readable.
    with path.open("a") as fh:
        fh.write("{not json\n")
    assert last_history_entry(path)["passed"] == 10


def test_summarize_carries_corpus_fingerprint():
    summary = _summary()
    summary["corpus"] = {"fingerprint": "abc123", "documents": 20, "chunks": 117}
    entry = summarize_for_history(summary)
    assert entry["corpus_fingerprint"] == "abc123"
    assert summarize_for_history(_summary())["corpus_fingerprint"] is None


def test_corpus_drifted_flags_fingerprint_change_only():
    prev = {"corpus_fingerprint": "aaa"}
    same = {"corpus_fingerprint": "aaa"}
    changed = {"corpus_fingerprint": "bbb"}
    assert corpus_drifted(None, changed) is False  # first run is not drift
    assert corpus_drifted(prev, same) is False
    assert corpus_drifted(prev, changed) is True
    # Missing fingerprints on either side (older entries) still compare.
    assert corpus_drifted({}, changed) is True
    assert corpus_drifted(prev, {}) is True
