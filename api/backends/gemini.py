"""Gemini via ``google-genai`` (Realistic mode). The model name comes from config only."""

import importlib
import importlib.util

import httpx
from google import genai
from google.genai import errors, types
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential
from tenacity.wait import WaitBaseT

from api.backends.base import TRANSIENT_STATUS, BackendError, ChatMessage


def _transport_errors() -> tuple[type[Exception], ...]:
    """Connection-level failures. The SDK may run on ``httpx`` or its ``httpx2`` fork."""
    found: list[type[Exception]] = [httpx.TransportError]
    if importlib.util.find_spec("httpx2") is not None:
        found.append(importlib.import_module("httpx2").TransportError)
    return tuple(found)


TRANSPORT_ERRORS = _transport_errors()


def transient(exc: BaseException) -> bool:
    """Worth retrying: rate limits, server errors and dropped connections."""
    if isinstance(exc, errors.APIError):
        return exc.code in TRANSIENT_STATUS
    return isinstance(exc, TRANSPORT_ERRORS)


class GeminiBackend:
    wait: WaitBaseT = wait_exponential(multiplier=2, min=2, max=60)
    attempts = 5

    def __init__(self, api_key: str, model: str, thinking_tokens: int = 0) -> None:
        """``thinking_tokens`` is added to every request's output limit. Models that reason
        before answering count those hidden tokens against ``max_output_tokens``; without
        the allowance a long prompt can use the whole limit and return empty text."""
        if not model:
            raise BackendError("REALISTIC_MODEL is not set")
        self.model = model
        self.thinking_tokens = thinking_tokens
        self._client = genai.Client(api_key=api_key)

    async def _generate(
        self, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        return await self._client.aio.models.generate_content(
            model=self.model, contents=contents, config=config
        )

    async def chat(self, messages: list[ChatMessage], max_tokens: int) -> str:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in messages
            if m.role != "system"
        ]
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            max_output_tokens=max_tokens + self.thinking_tokens,
            temperature=0.2,
        )
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(transient),
                wait=self.wait,
                stop=stop_after_attempt(self.attempts),
                reraise=True,
            ):
                with attempt:
                    resp = await self._generate(contents, config)
        except errors.APIError as exc:
            raise BackendError(f"gemini returned {exc.code}") from exc
        except TRANSPORT_ERRORS as exc:
            raise BackendError(f"gemini unreachable: {type(exc).__name__}") from exc
        text = resp.text
        if not text or not text.strip():
            raise BackendError("empty reply")
        return text
