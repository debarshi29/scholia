"""Chat backend protocol. Only ``api/proxy.py`` calls backends (invariant 2)."""

from typing import Literal, Protocol

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class BackendError(RuntimeError):
    """The model could not produce a reply (unreachable, rejected, empty)."""


class ChatBackend(Protocol):
    model: str
    """Model name, from config only (invariant 10)."""

    async def chat(self, messages: list[ChatMessage], max_tokens: int) -> str: ...


TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})
