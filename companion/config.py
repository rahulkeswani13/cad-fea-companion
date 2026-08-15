"""Application settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
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

    docs_dir: Path = Field(default_factory=lambda: ROOT / "docs")
    data_dir: Path = Field(default_factory=lambda: ROOT / "data")
    workspace_dir: Path = Field(default_factory=lambda: ROOT / "data" / "workspace")
    vectorstore_dir: Path = Field(default_factory=lambda: ROOT / "data" / "vectorstore")
    results_dir: Path = Field(default_factory=lambda: ROOT / "data" / "results")
    exports_dir: Path = Field(default_factory=lambda: ROOT / "data" / "exports")

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
