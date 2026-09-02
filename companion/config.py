"""Application settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    freecad_cmd: str = ""
    host: str = "127.0.0.1"
    port: int = 8000
    fem_allow_analytical_fallback: bool = True

    # LangGraph agent loop
    agent_max_tool_rounds: int = 6
    agent_require_tool_confirm: bool = False
    allow_remote: bool = False

    # H6: offline mode — when no LLM is configured (or it omits tools on a
    # first visit), the deterministic HeuristicRouter plans CAD/FEA tools.
    # Disabling it makes a key-less server answer RAG-only with no tool calls.
    heuristic_fallback: bool = True

    # RAG grounding label (ADR-012): 'strong' requires the fused top hit to
    # clear the TF-IDF cosine floor OR sit within the BM25 top-N.
    rag_grounding_min_tfidf: float = 0.05
    rag_grounding_bm25_top: int = 3

    docs_dir: Path = Field(default_factory=lambda: ROOT / "docs")

    # ADR-014: curated RAG corpus — allowlist ingestion. Only files under the
    # declared dirs (relative to ROOT) are ingested; everything else fails
    # closed. Comma-separated in env: RAG_CORPUS_DIRS=docs/reference,docs/adr
    rag_corpus_dirs: list[str] = Field(
        default_factory=lambda: ["docs/reference", "docs/adr"]
    )
    data_dir: Path = Field(default_factory=lambda: ROOT / "data")
    workspace_dir: Path = Field(default_factory=lambda: ROOT / "data" / "workspace")
    vectorstore_dir: Path = Field(default_factory=lambda: ROOT / "data" / "vectorstore")
    results_dir: Path = Field(default_factory=lambda: ROOT / "data" / "results")
    exports_dir: Path = Field(default_factory=lambda: ROOT / "data" / "exports")

    @field_validator("rag_corpus_dirs", mode="before")
    @classmethod
    def _split_corpus_dirs(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.workspace_dir,
            self.vectorstore_dir,
            self.results_dir,
            self.exports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def llm_configured(self) -> bool:
        return bool(self.gemini_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
