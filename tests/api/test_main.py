import asyncio
import json

from starlette.exceptions import HTTPException
from starlette.requests import Request

from api.main import app, http_error_handler


def test_health_route_registered() -> None:
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/health" in paths


def test_http_errors_use_envelope() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    resp = asyncio.run(http_error_handler(request, HTTPException(404, "Not Found")))
    assert resp.status_code == 404
    assert json.loads(bytes(resp.body)) == {"error": {"code": "not_found", "message": "Not Found"}}
