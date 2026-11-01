"""FastAPI app. Routers are added per milestone (sessions in M2, proxy in M3, debrief in M4)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.config import get_settings
from api.db import init_db, make_engine
from api.log import configure_logging


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    """Error envelope from CLAUDE.md §10: ``{"error": {"code", "message"}}``."""
    return {"error": {"code": code, "message": message}}


async def http_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = exc.detail if isinstance(exc.detail, str) else "http_error"
    slug = code.lower().replace(" ", "_")
    return JSONResponse(error_body(slug, str(exc.detail)), status_code=exc.status_code)


async def validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(error_body("validation_error", str(exc.errors())), status_code=422)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.db_url)
    init_db(engine)
    app.state.engine = engine
    yield
    engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Scholia", version="0.1.0", lifespan=lifespan)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
