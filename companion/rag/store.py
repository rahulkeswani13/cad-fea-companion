"""Local TF-IDF vector store for RAG (works without an API key)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from companion.config import get_settings


@dataclass
class Chunk:
    chunk_id: str
    source: str
    text: str


class LocalTfidfStore:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.vectorizer = TfidfVectorizer(stop_words="english", max_features=4096)
        self.matrix = None

    @property
    def path(self) -> Path:
        return get_settings().vectorstore_dir / "tfidf_store.json"

    def clear(self) -> None:
        self.chunks = []
        self.matrix = None

    def add_chunks(self, chunks: list[Chunk]) -> None:
        self.chunks.extend(chunks)

    def build(self) -> None:
        if not self.chunks:
            self.matrix = None
            return
        texts = [c.text for c in self.chunks]
        self.matrix = self.vectorizer.fit_transform(texts)
        self.save()

    def save(self) -> None:
        payload = {
            "chunks": [
                {"chunk_id": c.chunk_id, "source": c.source, "text": c.text}
                for c in self.chunks
            ]
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self) -> bool:
        if not self.path.exists():
            return False
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.chunks = [Chunk(**item) for item in payload.get("chunks", [])]
        if self.chunks:
            self.matrix = self.vectorizer.fit_transform([c.text for c in self.chunks])
        return bool(self.chunks)

    def search(self, query: str, k: int = 4) -> list[dict[str, Any]]:
        if not self.chunks:
            if not self.load():
                return []
        if self.matrix is None:
            return []
        q = self.vectorizer.transform([query])
        scores = cosine_similarity(q, self.matrix).ravel()
        idxs = scores.argsort()[::-1][:k]
        results = []
        for i in idxs:
            if scores[i] <= 0:
                continue
            chunk = self.chunks[int(i)]
            results.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "text": chunk.text,
                    "score": float(scores[i]),
                }
            )
        return results


_STORE: LocalTfidfStore | None = None


def get_store() -> LocalTfidfStore:
    global _STORE
    if _STORE is None:
        _STORE = LocalTfidfStore()
        _STORE.load()
    return _STORE


def chunk_text(text: str, source: str, max_chars: int = 800) -> list[Chunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[Chunk] = []
    buf = ""
    idx = 0
    for para in paragraphs:
        if len(buf) + len(para) + 1 <= max_chars:
            buf = f"{buf}\n\n{para}".strip()
            continue
        if buf:
            chunks.append(Chunk(chunk_id=f"{source}::{idx}", source=source, text=buf))
            idx += 1
        if len(para) <= max_chars:
            buf = para
        else:
            for start in range(0, len(para), max_chars):
                piece = para[start : start + max_chars]
                chunks.append(
                    Chunk(chunk_id=f"{source}::{idx}", source=source, text=piece)
                )
                idx += 1
            buf = ""
    if buf:
        chunks.append(Chunk(chunk_id=f"{source}::{idx}", source=source, text=buf))
    return chunks


def ingest_docs(docs_dir: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    docs_dir = docs_dir or settings.docs_dir
    store = get_store()
    store.clear()
    files = sorted(docs_dir.glob("**/*"))
    ingested = []
    for path in files:
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        source = str(path.relative_to(settings.docs_dir.parent))
        chunks = chunk_text(text, source=source)
        store.add_chunks(chunks)
        ingested.append({"path": source, "chunks": len(chunks)})
    store.build()
    return {"ok": True, "documents": ingested, "total_chunks": len(store.chunks)}


def retrieve(query: str, k: int = 4) -> list[dict[str, Any]]:
    return get_store().search(query, k=k)
