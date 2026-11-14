"""A complete app on a temp DB and temp problems dir, with fake model backends."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from api.backends.base import BackendError, ChatMessage
from api.config import get_settings
from api.deps import get_grader, get_proxy
from api.grader.judge import Judge
from api.grader.run import Grader
from api.main import create_app
from api.problems import ProblemStore
from api.proxy import Proxy
from corpus.publish import Draft, publish
from schema import Bug, BugCategory, Source

CORE = "".join(f"core_line_{i} = {i}\n" for i in range(1, 201))
UTIL = "".join(f"util_line_{i} = {i}\n" for i in range(1, 161))

SECRETS = (
    "SECRET_MECHANISM",
    "SECRET_FIX_DIFF",
    "SECRET_TEST_PATCH",
    "SECRET_KILLING_TEST",
    "SECRET_DESIGN_NOTE",
    "secret-upstream",
    "5ec2e7c0mm17",
)
"""Strings that exist only in answer.json, tests/ or the hidden parts of meta.json."""


class CharCounter:
    name = "chars"

    def count(self, text: str) -> int:
        return len(text)


class FakeBackend:
    def __init__(self, model: str) -> None:
        self.model = model
        self.fail = False
        self.replies: list[str] = []
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage], max_tokens: int) -> str:
        self.calls.append(messages)
        if self.fail:
            raise BackendError("backend down")
        return self.replies.pop(0) if self.replies else f"reply from {self.model}"


def publish_fixture(
    problems: Path,
    n: int,
    category: BugCategory = BugCategory.BOUNDARY,
    source: Source = Source.SWEBENCH,
    licence: str = "BSD-3-Clause",
    design_notes: bool = True,
) -> str:
    pub = publish(
        problems,
        Draft(
            tier=0,
            source=source,
            upstream_id=f"secret-upstream-{n}",
            origin_repo="org/repo",
            commit="5ec2e7c0mm17" + "0" * 28,
            licence=licence,
            files={"pkg/core.py": CORE, "pkg/util.py": UTIL},
            bugs=[
                Bug(
                    id="b1",
                    file="pkg/core.py",
                    lines=(50, 52),
                    category=category,
                    mechanism="SECRET_MECHANISM off by one in the loop bound.",
                    fix_diff="--- a/pkg/core.py\n+++ b/pkg/core.py\nSECRET_FIX_DIFF\n",
                    killing_test="tests/test_core.py::SECRET_KILLING_TEST",
                )
            ],
            design_notes=["SECRET_DESIGN_NOTE inject the bound."] if design_notes else [],
            tests={"test_patch.diff": "SECRET_TEST_PATCH\n"},
        ),
    )
    return pub.meta.problem_id


@dataclass
class Lab:
    client: httpx.AsyncClient
    engine: AsyncEngine
    problems: Path
    proxy: Proxy
    local: FakeBackend
    remote: FakeBackend
    judge: FakeBackend
    grader: Grader
    app: Any
    problem_ids: list[str] = field(default_factory=list)

    async def start(self, **body: object) -> dict[str, Any]:
        resp = await self.client.post("/api/sessions", json=body)
        assert resp.status_code == 201, resp.text
        data: dict[str, Any] = resp.json()
        return data


@pytest.fixture
async def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Lab]:
    monkeypatch.chdir(tmp_path)  # no .env here: tests never see real keys
    for var in ("GEMINI_API_KEY", "GEMINI_MODEL", "JUDGE_MODEL", "REALISTIC_MODEL"):
        monkeypatch.delenv(var, raising=False)
    problems = tmp_path / "problems"
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "scholia.db"))
    monkeypatch.setenv("PROBLEMS_DIR", str(problems))
    monkeypatch.setenv("LIBRARY_TOPICS", "")  # fixture repos have no topic
    ids = [
        publish_fixture(problems, 1, BugCategory.BOUNDARY, Source.SWEBENCH),
        publish_fixture(problems, 2, BugCategory.CONCURRENCY, Source.BUGSINPY, design_notes=False),
    ]
    get_settings.cache_clear()
    settings = get_settings()
    local, remote = FakeBackend("fake-qwen"), FakeBackend("fake-gemini")
    proxy = Proxy(
        settings=settings,
        counter=CharCounter(),
        local=local,
        realistic=remote,
        store=ProblemStore(problems),
    )
    app = create_app()
    app.dependency_overrides[get_proxy] = lambda: proxy
    judge = FakeBackend("fake-judge")  # default reply is not JSON, so scores stay ungraded
    async with app.router.lifespan_context(app):
        store = ProblemStore(problems)
        grader = Grader(app.state.engine, settings, store, Judge(judge, settings.judge_max_tokens))
        app.dependency_overrides[get_grader] = lambda: grader
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            yield Lab(
                client, app.state.engine, problems, proxy, local, remote, judge, grader, app, ids
            )
    get_settings.cache_clear()
