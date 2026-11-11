import json
from typing import Any

import httpx
import pytest
from google.genai import errors, types
from tenacity import wait_none

from api.backends.base import BackendError, ChatMessage
from api.backends.gemini import GeminiBackend
from api.backends.ollama import OllamaBackend
from api.config import Settings

pytestmark = pytest.mark.anyio

MSGS = [
    ChatMessage(role="system", content="You are a code assistant."),
    ChatMessage(role="user", content="What does line 3 do?"),
]


def _ollama(handler: Any) -> OllamaBackend:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    backend = OllamaBackend("http://ollama.test/v1/", "qwen-test", client=client)
    backend.wait = wait_none()
    return backend


def _ok(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


async def test_ollama_sends_openai_chat_request() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return _ok("It adds one.")

    assert await _ollama(handler).chat(MSGS, max_tokens=64) == "It adds one."
    [req] = seen
    assert str(req.url) == "http://ollama.test/v1/chat/completions"
    body = json.loads(req.content)
    assert body["model"] == "qwen-test"
    assert body["max_tokens"] == 64
    assert body["stream"] is False
    assert body["messages"] == [m.model_dump() for m in MSGS]


async def test_ollama_retries_transient_errors() -> None:
    replies = iter([httpx.Response(503), httpx.Response(429), _ok("ok")])
    assert await _ollama(lambda req: next(replies)).chat(MSGS, 8) == "ok"


async def test_ollama_gives_up_on_client_error() -> None:
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    with pytest.raises(BackendError, match="400"):
        await _ollama(handler).chat(MSGS, 8)
    assert calls == 1


async def test_ollama_unreachable_is_backend_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)

    with pytest.raises(BackendError, match="unreachable"):
        await _ollama(handler).chat(MSGS, 8)


@pytest.mark.parametrize(
    "payload", [{"choices": []}, {"choices": [{"message": {"content": "  "}}]}, {}]
)
async def test_ollama_malformed_or_empty(payload: dict[str, Any]) -> None:
    with pytest.raises(BackendError):
        await _ollama(lambda req: httpx.Response(200, json=payload)).chat(MSGS, 8)


class _FakeGenerate:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, contents: Any, config: Any) -> Any:
        self.calls.append({"contents": contents, "config": config})
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def _gemini(monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> tuple[GeminiBackend, Any]:
    backend = GeminiBackend(api_key="k", model="gemini-test")
    backend.wait = wait_none()
    fake = _FakeGenerate(outcomes)
    monkeypatch.setattr(backend, "_generate", fake)
    return backend, fake


class _Resp:
    def __init__(self, text: str | None) -> None:
        self.text = text


async def test_gemini_maps_system_prompt_and_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    backend, fake = _gemini(monkeypatch, [_Resp("Whole-file answer.")])
    assert await backend.chat(MSGS, max_tokens=100) == "Whole-file answer."
    [call] = fake.calls
    assert backend.model == "gemini-test"
    config: types.GenerateContentConfig = call["config"]
    assert config.system_instruction == "You are a code assistant."
    assert config.max_output_tokens == 100
    [content] = call["contents"]
    assert content.role == "user"
    assert content.parts[0].text == "What does line 3 do?"


async def test_gemini_retries_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    backend, fake = _gemini(monkeypatch, [errors.APIError(429, {}), _Resp("ok")])
    assert await backend.chat(MSGS, 10) == "ok"
    assert len(fake.calls) == 2


async def test_gemini_client_error_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    backend, fake = _gemini(monkeypatch, [errors.APIError(400, {})])
    with pytest.raises(BackendError, match="400"):
        await backend.chat(MSGS, 10)
    assert len(fake.calls) == 1


async def test_gemini_empty_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    backend, _ = _gemini(monkeypatch, [_Resp(None)])
    with pytest.raises(BackendError, match="empty"):
        await backend.chat(MSGS, 10)


def test_gemini_requires_configured_model() -> None:
    with pytest.raises(BackendError, match="REALISTIC_MODEL"):
        GeminiBackend(api_key="k", model="")


@pytest.mark.live
async def test_live_ollama() -> None:
    s = Settings()
    backend = OllamaBackend(s.ollama_base_url, s.local_model)
    try:
        reply = await backend.chat(MSGS, max_tokens=64)
    finally:
        await backend.aclose()
    assert reply.strip()


@pytest.mark.live
async def test_live_gemini() -> None:
    s = Settings()
    if s.gemini_api_key is None or not s.realistic_model:
        pytest.skip("GEMINI_API_KEY / REALISTIC_MODEL not set")
    backend = GeminiBackend(s.gemini_api_key.get_secret_value(), s.realistic_model)
    assert (await backend.chat(MSGS, max_tokens=64)).strip()


async def test_gemini_retries_dropped_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    dropped = httpx.RemoteProtocolError("Server disconnected without sending a response.")
    backend, fake = _gemini(monkeypatch, [dropped, _Resp("ok")])
    assert await backend.chat(MSGS, 10) == "ok"
    assert len(fake.calls) == 2


async def test_gemini_unreachable_is_backend_error(monkeypatch: pytest.MonkeyPatch) -> None:
    backend, _ = _gemini(monkeypatch, [httpx.ConnectError("no route")] * 5)
    with pytest.raises(BackendError, match="unreachable"):
        await backend.chat(MSGS, 10)


async def test_gemini_adds_the_thinking_allowance(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = GeminiBackend(api_key="k", model="gemini-test", thinking_tokens=2048)
    fake = _FakeGenerate([_Resp("ok")])
    monkeypatch.setattr(backend, "_generate", fake)
    await backend.chat(MSGS, max_tokens=512)
    assert fake.calls[0]["config"].max_output_tokens == 2560
