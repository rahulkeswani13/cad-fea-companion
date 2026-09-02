"""H13: judge best-of-3 — FAIL triggers 2-of-3 majority re-sampling."""

from __future__ import annotations

import eval.judge as judge_mod
from eval.judge import judge_agent_case

_CASE = {"id": "x", "message": "m", "type": "agent"}


def _sample(pass_value, usage=None, verdict="graded"):
    return {
        "model": "m",
        "usage": usage,
        "pass": pass_value,
        "verdict": verdict,
        "scores": {"honesty": 4},
        "notes": "n",
    }


def _script(monkeypatch, samples):
    calls = {"n": 0}

    def fake_once(case, answer, tool_names, api_key, model):
        idx = min(calls["n"], len(samples) - 1)
        calls["n"] += 1
        return samples[idx]

    monkeypatch.setattr(judge_mod, "_judge_once", fake_once)
    return calls


def test_passing_first_sample_is_single_call(monkeypatch):
    calls = _script(monkeypatch, [_sample(True, {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})])
    out = judge_agent_case(_CASE, "answer", [], "key", "model")
    assert out["pass"] is True
    assert out["best_of_3"] is False
    assert calls["n"] == 1
    assert out["usage"]["total_tokens"] == 12


def test_fail_resamples_twice_and_majority_decides(monkeypatch):
    calls = _script(
        monkeypatch,
        [
            _sample(False, {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11}),
            _sample(False, {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11}),
            _sample(True, {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11}),
        ],
    )
    out = judge_agent_case(_CASE, "answer", [], "key", "model")
    assert calls["n"] == 3
    assert out["pass"] is False  # 2-of-3 fail votes
    assert out["best_of_3"] is True
    assert out["usage"]["total_tokens"] == 33  # extra sampling tokens recorded
    assert [s["pass"] for s in out["samples"]] == [False, False, True]


def test_overturned_fail_two_passes(monkeypatch):
    _script(
        monkeypatch,
        [
            _sample(False, {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6}),
            _sample(True, {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6}),
            _sample(True, {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6}),
        ],
    )
    out = judge_agent_case(_CASE, "answer", [], "key", "model")
    assert out["pass"] is True  # majority overturns the noisy FAIL
    assert out["best_of_3"] is True


def test_no_majority_keeps_first_verdict(monkeypatch):
    _script(
        monkeypatch,
        [
            _sample(False, verdict="graded"),
            _sample(True),
            _sample(None, verdict="unparsed"),
        ],
    )
    out = judge_agent_case(_CASE, "answer", [], "key", "model")
    assert out["pass"] is False
    assert out["best_of_3"] is True
    assert out["verdict"] == "graded"  # first sample's verdict survives


def test_error_samples_never_raise(monkeypatch):
    _script(
        monkeypatch,
        [
            _sample(False),
            _sample(None, verdict="error"),
            _sample(None, verdict="error"),
        ],
    )
    out = judge_agent_case(_CASE, "answer", [], "key", "model")
    assert out["pass"] is False
    assert out["verdict"] == "graded"


def test_missing_usage_degrades_to_none(monkeypatch):
    _script(monkeypatch, [_sample(False, usage=None), _sample(True), _sample(True)])
    out = judge_agent_case(_CASE, "answer", [], "key", "model")
    assert out["pass"] is True
    assert out["usage"] is None
