"""Gemini via ``google-genai`` (Realistic mode). The model name comes from config only."""

from google import genai
from google.genai import errors, types
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential
from tenacity.wait import WaitBaseT

from api.backends.base import TRANSIENT_STATUS, BackendError, ChatMessage


def _transient(exc: BaseException) -> bool:
    return isinstance(exc, errors.APIError) and exc.code in TRANSIENT_STATUS


class GeminiBackend:
    wait: WaitBaseT = wait_exponential(multiplier=2, min=2, max=60)
    attempts = 5

    def __init__(self, api_key: str, model: str) -> None:
        if not model:
            raise BackendError("REALISTIC_MODEL is not set")
        self.model = model
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
            max_output_tokens=max_tokens,
            temperature=0.2,
        )
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception(_transient),
                wait=self.wait,
                stop=stop_after_attempt(self.attempts),
                reraise=True,
            ):
                with attempt:
                    resp = await self._generate(contents, config)
        except errors.APIError as exc:
            raise BackendError(f"gemini returned {exc.code}") from exc
        text = resp.text
        if not text or not text.strip():
            raise BackendError("empty reply")
        return text
