"""Application settings. Model names, caps and budgets come ONLY from here (invariant 10)."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from corpus.topics import Topic, parse_topics


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Cloud (Gemini): judge + Realistic mode
    gemini_api_key: SecretStr | None = None
    gemini_model: str = ""
    """Fallback for ``judge_model`` and ``realistic_model`` when those are not set."""
    judge_model: str = ""
    realistic_model: str = ""

    @model_validator(mode="before")
    @classmethod
    def _gemini_model_fallback(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("gemini_model"):
            for key in ("judge_model", "realistic_model"):
                if not data.get(key):
                    data[key] = data["gemini_model"]
        return data

    # Local (Ollama): Constrained mode
    ollama_base_url: str = "http://localhost:11434/v1"
    local_model: str = "qwen2.5-coder:3b"
    local_tokenizer: str = "Qwen/Qwen2.5-Coder-3B-Instruct"

    # Session defaults
    default_ctx_cap: int = Field(default=3072, gt=0)
    default_q_budget: int = Field(default=12, ge=0)
    session_minutes: int = Field(default=60, gt=0)
    max_reply_tokens: int = Field(default=512, gt=0)
    """Upper bound on an assistant reply, both modes."""
    max_question_chars: int = Field(default=1000, gt=0)
    """Longest question accepted; stops pasting code into the question to dodge the cap."""

    # Grader
    match_tolerance_lines: int = Field(default=3, ge=0)
    judge_max_tokens: int = Field(default=700, gt=0)
    gemini_thinking_tokens: int = Field(default=2048, ge=0)
    """Extra output-token allowance for the Gemini model's hidden reasoning, on top of
    ``max_reply_tokens`` / ``judge_max_tokens``."""

    # Corpus
    library_topics: str = "ml,scientific,math"
    """Topics to build and show (see ``corpus/topics.py``). Empty means every topic."""

    @property
    def topics(self) -> frozenset[Topic]:
        return parse_topics(self.library_topics)

    @field_validator("library_topics")
    @classmethod
    def _known_topics(cls, value: str) -> str:
        parse_topics(value)  # raises ValueError on an unknown topic name
        return value

    # Storage
    db_path: Path = Path("data/scholia.db")
    problems_dir: Path = Path("problems")

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path.as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
