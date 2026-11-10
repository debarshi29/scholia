"""FastAPI app. Routers are added per milestone (sessions in M2, proxy in M3, debrief in M4)."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.backends.ollama import OllamaBackend
from api.config import get_settings
from api.db import init_db, make_engine
from api.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    validation_error_handler,
)
from api.log import configure_logging
from api.sessions import router as sessions_router
from corpus.publish import register, scan


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.db_url)
    await init_db(engine)
    # problems/ is the source of truth; the index table is rebuilt from it on every start.
    await register(engine, await asyncio.to_thread(scan, settings.problems_dir))
    app.state.engine = engine
    app.state.proxy = None
    yield
    proxy = app.state.proxy
    local = getattr(proxy, "local", None)
    if isinstance(local, OllamaBackend):
        await local.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Scholia", version="0.1.0", lifespan=lifespan)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(sessions_router)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
