"""Shared FastAPI dependencies."""

import asyncio

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine

from api.backends.base import ChatBackend
from api.backends.gemini import GeminiBackend
from api.backends.ollama import OllamaBackend
from api.config import Settings, get_settings
from api.grader.judge import Judge
from api.grader.run import Grader
from api.problems import ProblemStore
from api.proxy import Proxy
from api.tokens import HFTokenCounter

_lock = asyncio.Lock()


async def build_proxy(settings: Settings) -> Proxy:
    """Loads the Qwen tokenizer (may download once) off the event loop."""
    counter = await asyncio.to_thread(HFTokenCounter, settings.local_tokenizer)
    realistic: ChatBackend | None = None
    if settings.gemini_api_key is not None and settings.realistic_model:
        realistic = GeminiBackend(
            settings.gemini_api_key.get_secret_value(), settings.realistic_model
        )
    return Proxy(
        settings=settings,
        counter=counter,
        local=OllamaBackend(settings.ollama_base_url, settings.local_model),
        realistic=realistic,
        store=ProblemStore(settings.problems_dir),
    )


async def get_proxy(request: Request) -> Proxy:
    """Built on first use and cached on the app, so startup needs no network."""
    state = request.app.state
    if getattr(state, "proxy", None) is None:
        async with _lock:
            if getattr(state, "proxy", None) is None:
                state.proxy = await build_proxy(get_settings())
    proxy: Proxy = state.proxy
    return proxy


def get_store() -> ProblemStore:
    return ProblemStore(get_settings().problems_dir)


def build_grader(settings: Settings, engine: AsyncEngine) -> Grader:
    backend: ChatBackend | None = None
    if settings.gemini_api_key is not None and settings.judge_model:
        backend = GeminiBackend(settings.gemini_api_key.get_secret_value(), settings.judge_model)
    return Grader(
        engine=engine,
        settings=settings,
        store=ProblemStore(settings.problems_dir),
        judge=Judge(backend, settings.judge_max_tokens),
    )


def get_grader(request: Request) -> Grader:
    state = request.app.state
    if getattr(state, "grader", None) is None:
        state.grader = build_grader(get_settings(), state.engine)
    grader: Grader = state.grader
    return grader
