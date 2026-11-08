"""Ollama through its OpenAI-compatible endpoint (``OLLAMA_BASE_URL``, e.g. ``.../v1``).

Note: the OpenAI-compatible endpoint cannot set ``num_ctx``; the proxy keeps prompts
within ``ctx_cap``, which must not exceed the model's configured context in Ollama.
"""

from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential
from tenacity.wait import WaitBaseT

from api.backends.base import TRANSIENT_STATUS, BackendError, ChatMessage


def _transient(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in TRANSIENT_STATUS


class OllamaBackend:
    wait: WaitBaseT = wait_exponential(multiplier=1, min=1, max=20)
    attempts = 4

    def __init__(self, base_url: str, model: str, client: httpx.AsyncClient | None = None) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0))

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post(self._url, json=body)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    async def chat(self, messages: list[ChatMessage], max_tokens: int) -> str:
        body = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "stream": False,
        }
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_transient),
                wait=self.wait,
                stop=stop_after_attempt(self.attempts),
                reraise=True,
            ):
                with attempt:
                    data = await self._post(body)
        except httpx.HTTPStatusError as exc:
            raise BackendError(f"ollama returned {exc.response.status_code}") from exc
        except httpx.TransportError as exc:
            raise BackendError(f"ollama unreachable at {self._url}: {exc}") from exc
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError("malformed ollama response") from exc
        if not isinstance(text, str) or not text.strip():
            raise BackendError("empty reply")
        return text

    async def aclose(self) -> None:
        await self._client.aclose()
