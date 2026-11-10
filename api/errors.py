"""API errors. Every error response is ``{"error": {"code", "message"}}`` (CLAUDE.md §10)."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


async def api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status)


async def http_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = exc.detail if isinstance(exc.detail, str) else "http_error"
    slug = code.lower().replace(" ", "_")
    return JSONResponse(error_body(slug, str(exc.detail)), status_code=exc.status_code)


async def validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(error_body("validation_error", str(exc.errors())), status_code=422)
