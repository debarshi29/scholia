"""Application settings. Model names, caps and budgets come ONLY from here (invariant 10)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Cloud (Gemini): judge + Realistic mode
    gemini_api_key: SecretStr | None = None
    judge_model: str = ""
    realistic_model: str = ""

    # Local (Ollama): Constrained mode
    ollama_base_url: str = "http://localhost:11434/v1"
    local_model: str = "qwen2.5-coder:3b"
    local_tokenizer: str = "Qwen/Qwen2.5-Coder-3B-Instruct"

    # Session defaults
    default_ctx_cap: int = Field(default=3072, gt=0)
    default_q_budget: int = Field(default=12, ge=0)
    session_minutes: int = Field(default=60, gt=0)

    # Grader
    match_tolerance_lines: int = Field(default=3, ge=0)

    # Storage
    db_path: Path = Path("data/scholia.db")
    problems_dir: Path = Path("problems")

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path.as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
