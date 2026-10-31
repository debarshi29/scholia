"""Session-level enums shared by the API, DB and frontend."""

from enum import StrEnum


class AssistantMode(StrEnum):
    CONSTRAINED = "constrained"
    """Local Qwen via Ollama; sees only the selected lines, token cap and question budget."""
    REALISTIC = "realistic"
    """Gemini with the whole file in context; no budget."""
