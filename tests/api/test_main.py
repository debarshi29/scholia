from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from api.config import get_settings
from api.main import create_app

pytestmark = pytest.mark.anyio


@pytest.fixture
async def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "scholia.db"))
    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    get_settings.cache_clear()


async def test_health(client: httpx.AsyncClient, tmp_path: Path) -> None:
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    # Lifespan created the DB file under the configured path.
    assert (tmp_path / "data" / "scholia.db").exists()


async def test_unknown_route_uses_error_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.json() == {"error": {"code": "not_found", "message": "Not Found"}}
