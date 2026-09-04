"""Console API tests: /app + the ADR-015 read-only endpoints (prompts,
design-program, runs, solver-status). Endpoint behavior must not depend on
workspace files existing (CI has none)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from companion.main import (
    PROMPTS_PATH,
    _load_prompts,
    _program_payload,
    _run_row,
    _run_rows,
    app,
)

client = TestClient(app)


# --- /app (console shell; works for built and placeholder paths) ---


def test_app_serves_html():
    res = client.get("/app")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "CAD/FEA Companion" in res.text


# --- /api/prompts ---


def test_prompts_library_shape():
    res = client.get("/api/prompts")
    assert res.status_code == 200
    data = res.json()
    assert data["version"]
    assert len(data["categories"]) >= 3
    assert len(data["features"]) >= 8
    for cat in data["categories"]:
        assert cat["id"] and cat["title"]
        assert len(cat["items"]) >= 1
        for item in cat["items"]:
            assert item["id"] and item["title"] and item["prompt"].strip()
            assert item.get("cost") in (None, "instant", "seconds", "solve")
            assert isinstance(item.get("freecad"), bool)
    for feature in data["features"]:
        assert feature["id"] and feature["title"] and feature["blurb"]
        assert len(feature["steps"]) >= 2
        for step in feature["steps"]:
            assert step["title"] and step["prompt"].strip()
            assert isinstance(step["talking_points"], list) and step["talking_points"]


def test_prompts_library_ids_unique():
    data = _load_prompts()
    item_ids = [i["id"] for c in data["categories"] for i in c["items"]]
    assert len(item_ids) == len(set(item_ids))
    feature_ids = [f["id"] for f in data["features"]]
    assert len(feature_ids) == len(set(feature_ids))


def test_prompts_file_exists_on_disk():
    assert PROMPTS_PATH.exists()


def test_prompts_error_is_compact(monkeypatch):
    def boom() -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr("companion.main._load_prompts", boom)
    res = client.get("/api/prompts")
    assert res.status_code == 500
    body = res.json()
    assert body["error"] and body["correction"]
    assert "boom" not in body["error"]


# --- design-program payload shaping ---


def test_program_payload_success_flattens_sorted_params():
    result = {
        "ok": True,
        "part": "brake_pedal",
        "rev": 3,
        "params_hash": "ab12",
        "params": {"web_type": "xtruss", "cell_size_mm": 15},
    }
    payload = _program_payload(result)
    assert payload["ok"] is True
    assert payload["active_part"] is None or isinstance(payload["active_part"], str)
    assert payload["params"] == [
        {"key": "cell_size_mm", "value": 15},
        {"key": "web_type", "value": "xtruss"},
    ]


def test_program_payload_failure_is_envelope():
    result = {"ok": False, "error": "no program", "correction": "create one"}
    payload = _program_payload(result)
    assert payload["ok"] is False
    assert payload["error"] and payload["correction"]
    assert "params" not in payload


def test_design_program_endpoint_shape():
    res = client.get("/api/design-program")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body.get("ok"), bool)


# --- run rows compaction + /api/runs ---


def test_run_row_keeps_only_declared_keys():
    run = {
        "run_id": "r1",
        "part": "brake_pedal",
        "method": "calculix",
        "max_von_mises_mpa": 23.7,
        "divergence_flag": False,
        "secret_internal_field": "x",
    }
    row = _run_row(run)
    assert set(row) == {
        "run_id",
        "part",
        "method",
        "max_von_mises_mpa",
        "divergence_flag",
    }


def test_run_rows_sort_desc_and_cap(monkeypatch):
    synthetic = [
        {"run_id": "old", "part": "p", "ts": "2026-01-01T00:00:00Z"},
        {"run_id": "new", "part": "p", "ts": "2026-02-01T00:00:00Z"},
        {"run_id": "mid", "part": "p", "ts": "2026-01-15T00:00:00Z"},
        {"run_id": "no_ts", "part": "p"},
    ]
    monkeypatch.setattr("companion.main.read_runs", lambda part, last_n: synthetic)
    payload = _run_rows("p", limit=10)
    assert payload["part"] == "p"
    assert [r["run_id"] for r in payload["runs"]] == ["new", "mid", "old", "no_ts"]

    payload = _run_rows("p", limit=2)
    assert len(payload["runs"]) == 2
    assert payload["runs"][0]["run_id"] == "new"


def test_run_rows_unknown_part_is_empty(monkeypatch):
    monkeypatch.setattr("companion.main.read_runs", lambda part, last_n: [])
    payload = _run_rows("no_such_part_zz", limit=10)
    assert payload == {"part": "no_such_part_zz", "runs": []}


def test_runs_endpoint_limit_clamped():
    res = client.get("/api/runs", params={"limit": 2})
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["runs"], list) and len(body["runs"]) <= 2
    assert "part" in body

    res = client.get("/api/runs", params={"limit": 999})
    assert res.status_code == 200  # clamped to 50, no error


@pytest.mark.parametrize("bad_limit", ["0", "-5"])
def test_runs_endpoint_degenerate_limit(bad_limit):
    res = client.get("/api/runs", params={"limit": bad_limit})
    assert res.status_code == 200
    assert isinstance(res.json()["runs"], list)


# --- /api/solver-status ---


def test_solver_status_shape():
    res = client.get("/api/solver-status")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["freecad"], bool)
    assert isinstance(body["llm"], dict)
    assert isinstance(body["require_tool_confirm"], bool)
