"""RAG ingest: product corpus excludes internal roadmap files."""

from __future__ import annotations

from companion.rag.store import ingest_docs


def test_ingest_docs_skips_roadmap_files():
    result = ingest_docs()
    assert result["ok"] is True
    paths = [doc["path"] for doc in result["documents"]]
    assert "docs/PLAN.md" not in paths
    assert "docs/PLAN_F26.md" not in paths
    assert "docs/ARCHITECTURE.md" in paths
    assert "docs/materials.md" in paths
