"""Local hybrid retrieval: TF-IDF + BM25 fused with Reciprocal Rank Fusion.

Works without an API key and without any model download (ADR-012): both
retrievers are algorithmic, run in-process over the chunk list, and fuse by
rank only — no score normalization across retrievers. The fused hit keeps the
legacy ``score`` key (TF-IDF cosine) byte-compatible; per-retriever ranks,
BM25 scores, and the RRF score are additive fields.

Every search also returns a ``grounding`` label (``strong`` | ``weak`` |
``none``) computed from the fused top hit: the retrieval-side analogue of
solver honesty. A ``weak`` label means the corpus has no confident match and
the UI says so instead of dressing up noise.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from companion.config import ROOT, get_settings

# RRF fusion constants (standard k=60 damping) and per-retriever candidate depth.
_RRF_K = 60
_CANDIDATES = 10


@dataclass
class Chunk:
    chunk_id: str
    source: str
    text: str


def rrf_fuse(
    tfidf_rank: dict[int, int], bm25_rank: dict[int, int]
) -> list[tuple[int, float]]:
    """Fuse two retriever rankings into [(doc_idx, rrf_score)] sorted best-first.

    RRF: score = sum(1 / (k + rank)) over the retrievers that surfaced the doc.
    Rank-only fusion — no cross-retriever score normalization needed.
    """
    scores: dict[int, float] = {}
    for idx in set(tfidf_rank) | set(bm25_rank):
        total = 0.0
        if idx in tfidf_rank:
            total += 1.0 / (_RRF_K + tfidf_rank[idx])
        if idx in bm25_rank:
            total += 1.0 / (_RRF_K + bm25_rank[idx])
        scores[idx] = total
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def grounding_label(
    fused: list[dict[str, Any]], min_tfidf: float, bm25_top: int
) -> str:
    """Label retrieval confidence from the fused top hit.

    ``strong``: top hit clears the TF-IDF cosine floor OR sits in the BM25
    top-N. ``weak``: something came back but neither retriever is confident.
    ``none``: no hits at all.
    """
    if not fused:
        return "none"
    top = fused[0]
    tfidf_ok = float(top.get("score") or 0.0) >= min_tfidf
    bm25_rank = top.get("bm25_rank")
    bm25_ok = isinstance(bm25_rank, int) and 1 <= bm25_rank <= bm25_top
    return "strong" if (tfidf_ok or bm25_ok) else "weak"


class LocalTfidfStore:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.vectorizer = TfidfVectorizer(stop_words="english", max_features=4096)
        self.matrix = None
        self.bm25: Any | None = None
        self._analyzer: Any | None = None

    @property
    def path(self) -> Path:
        return get_settings().vectorstore_dir / "tfidf_store.json"

    def clear(self) -> None:
        self.chunks = []
        self.matrix = None
        self.bm25 = None
        self._analyzer = None

    def add_chunks(self, chunks: list[Chunk]) -> None:
        self.chunks.extend(chunks)

    def _tokenize(self, text: str) -> list[str]:
        if self._analyzer is None:
            self._analyzer = self.vectorizer.build_analyzer()
        return self._analyzer(text)

    def _build_bm25(self) -> None:
        from rank_bm25 import BM25Okapi

        corpus = [self._tokenize(c.text) for c in self.chunks]
        self.bm25 = BM25Okapi(corpus) if corpus else None

    def build(self) -> None:
        if not self.chunks:
            self.matrix = None
            self.bm25 = None
            return
        texts = [c.text for c in self.chunks]
        self.matrix = self.vectorizer.fit_transform(texts)
        self._build_bm25()
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
            self._build_bm25()
        return bool(self.chunks)

    def _rankings(self, query: str) -> tuple[dict[int, int], dict[int, int], list[float], list[float]]:
        """Full TF-IDF and BM25 rankings over the corpus.

        Returns (tfidf_rank, bm25_rank, tfidf_scores, bm25_scores) where the
        rank dicts are 1-based and limited to the candidate depth.
        """
        cos = cosine_similarity(
            self.vectorizer.transform([query]), self.matrix
        ).ravel()
        tfidf_order = [
            int(i) for i in cos.argsort()[::-1] if cos[i] > 0
        ][:_CANDIDATES]
        bm25_scores = self.bm25.get_scores(self._tokenize(query))
        bm25_order = [
            int(i)
            for i in sorted(range(len(bm25_scores)), key=lambda i: -bm25_scores[i])
            if bm25_scores[i] > 0
        ][:_CANDIDATES]
        tfidf_rank = {idx: r + 1 for r, idx in enumerate(tfidf_order)}
        bm25_rank = {idx: r + 1 for r, idx in enumerate(bm25_order)}
        return tfidf_rank, bm25_rank, cos, bm25_scores

    def _hit(
        self,
        idx: int,
        cos: list[float],
        bm25_scores: list[float],
        tfidf_rank: dict[int, int],
        bm25_rank: dict[int, int],
        fused_rank: int | None,
        rrf_score: float | None,
    ) -> dict[str, Any]:
        chunk = self.chunks[idx]
        methods = []
        if idx in tfidf_rank:
            methods.append("tfidf")
        if idx in bm25_rank:
            methods.append("bm25")
        return {
            "chunk_id": chunk.chunk_id,
            "source": chunk.source,
            "text": chunk.text,
            # Legacy key: TF-IDF cosine (back-compat for old callers/UI).
            "score": round(float(cos[idx]), 4),
            "methods": methods,
            "tfidf_rank": tfidf_rank.get(idx),
            "bm25_rank": bm25_rank.get(idx),
            "bm25_score": round(float(bm25_scores[idx]), 4)
            if idx in bm25_rank
            else None,
            "fused_rank": fused_rank,
            "rrf_score": round(float(rrf_score), 6) if rrf_score is not None else None,
        }

    def search_detail(self, query: str, k: int = 4) -> dict[str, Any]:
        """Per-retriever top lists + fused top-k + grounding label."""
        empty = {"grounding": "none", "tfidf": [], "bm25": [], "fused": []}
        if not self.chunks and not self.load():
            return empty
        if self.matrix is None or self.bm25 is None:
            return empty
        tfidf_rank, bm25_rank, cos, bm25_scores = self._rankings(query)
        fused = rrf_fuse(tfidf_rank, bm25_rank)[:k]
        hits = [
            self._hit(
                idx,
                cos,
                bm25_scores,
                tfidf_rank,
                bm25_rank,
                fused_rank=r + 1,
                rrf_score=score,
            )
            for r, (idx, score) in enumerate(fused)
        ]
        tfidf_hits = [
            self._hit(idx, cos, bm25_scores, tfidf_rank, bm25_rank, None, None)
            for idx in sorted(tfidf_rank, key=lambda i: tfidf_rank[i])
        ]
        bm25_hits = [
            self._hit(idx, cos, bm25_scores, tfidf_rank, bm25_rank, None, None)
            for idx in sorted(bm25_rank, key=lambda i: bm25_rank[i])
        ]
        return {
            "grounding": grounding_label(
                hits,
                get_settings().rag_grounding_min_tfidf,
                get_settings().rag_grounding_bm25_top,
            ),
            "tfidf": tfidf_hits,
            "bm25": bm25_hits,
            "fused": hits,
        }

    def search(self, query: str, k: int = 4) -> list[dict[str, Any]]:
        """Fused top-k hits (legacy list shape; hits carry additive rank fields)."""
        return self.search_detail(query, k=k)["fused"]

    def stats(self) -> dict[str, Any]:
        """Corpus/index inventory for the RAG Lab stats panel."""
        if not self.chunks:
            self.load()
        sources = Counter(c.source for c in self.chunks)
        updated_at: str | None = None
        if self.path.exists():
            from datetime import datetime

            updated_at = datetime.fromtimestamp(
                self.path.stat().st_mtime
            ).isoformat(timespec="seconds")
        return {
            "ok": True,
            "docs": len(sources),
            "chunks": len(self.chunks),
            "avg_chunk_chars": round(
                sum(len(c.text) for c in self.chunks) / len(self.chunks), 1
            )
            if self.chunks
            else 0,
            "sources": [
                {"path": path, "chunks": n}
                for path, n in sorted(sources.items())
            ],
            "index_updated_at": updated_at,
            "retrievers": ["tfidf", "bm25"],
        }


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


def _resolve_corpus_dirs(
    corpus_dirs: list[str] | list[Path] | None,
) -> list[Path]:
    settings = get_settings()
    raw = corpus_dirs if corpus_dirs is not None else settings.rag_corpus_dirs
    resolved = []
    for entry in raw:
        path = Path(entry)
        if not path.is_absolute():
            path = ROOT / path
        resolved.append(path)
    return resolved


def collect_corpus_files(
    corpus_dirs: list[str] | list[Path] | None = None,
) -> list[tuple[Path, str]]:
    """Deterministic (path, source) pairs under the declared corpus dirs.

    Pure selection logic — no store, no disk side effects — so the fail-closed
    allowlist property (ADR-014) is testable without touching global state.
    """
    resolved = _resolve_corpus_dirs(corpus_dirs)
    out: list[tuple[Path, str]] = []
    for root_dir in resolved:
        for path in sorted(root_dir.glob("**/*")):
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            try:
                source = str(path.resolve().relative_to(ROOT))
            except ValueError:
                source = str(path)
            out.append((path, source))
    return out


def ingest_docs(corpus_dirs: list[str] | list[Path] | None = None) -> dict[str, Any]:
    """Ingest only the declared corpus dirs (ADR-014 allowlist, fails closed).

    Files outside the declared corpus dirs — plans, notes, roadmap docs — are
    never ingested: new content defaults to excluded, and getting in is a
    deliberate act. Sources are repo-root-relative for paths under ROOT;
    out-of-tree dirs (tests) keep their absolute path as the source.
    """
    files = collect_corpus_files(corpus_dirs)
    store = get_store()
    store.clear()
    ingested = []
    for path, source in files:
        chunks = chunk_text(path.read_text(encoding="utf-8"), source=source)
        store.add_chunks(chunks)
        ingested.append({"path": source, "chunks": len(chunks)})
    store.build()
    return {
        "ok": True,
        "documents": ingested,
        "total_chunks": len(store.chunks),
        "corpus_dirs": [str(d) for d in _resolve_corpus_dirs(corpus_dirs)],
    }


def retrieve(query: str, k: int = 4) -> list[dict[str, Any]]:
    """Fused top-k hits (legacy shape + additive rank/grounding fields)."""
    return get_store().search(query, k=k)


def retrieve_detail(query: str, k: int = 4) -> dict[str, Any]:
    """Full hybrid breakdown: per-retriever rankings, fused hits, grounding."""
    return get_store().search_detail(query, k=k)
