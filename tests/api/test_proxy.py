"""Assistant proxy: invariants 2, 3, 4, 6 and 7."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.backends.base import BackendError, ChatMessage
from api.config import Settings, get_settings
from api.db import QueryRow, SessionRow, init_db, make_engine
from api.deps import get_proxy
from api.main import create_app
from api.problems import ProblemStore
from api.proxy import (
    SYSTEM_CONSTRAINED,
    SYSTEM_REALISTIC,
    AskRequest,
    AskResult,
    Proxy,
    RefusalReason,
)
from corpus.publish import Draft, index_row, publish
from schema import AssistantMode, Bug, BugCategory, Source

pytestmark = pytest.mark.anyio

CORE = "".join(f"core_line_{i} = {i}\n" for i in range(1, 201))
UTIL = "".join(f"util_line_{i} = {i}\n" for i in range(1, 161))


class CharCounter:
    name = "chars"

    def count(self, text: str) -> int:
        return len(text)


class FakeBackend:
    def __init__(self, model: str, fail: bool = False) -> None:
        self.model = model
        self.fail = fail
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage], max_tokens: int) -> str:
        self.calls.append(messages)
        if self.fail:
            raise BackendError("ollama unreachable")
        return f"reply from {self.model}"


def _publish(problems: Path, licence: str = "BSD-3-Clause") -> tuple[str, int]:
    pub = publish(
        problems,
        Draft(
            tier=0,
            source=Source.SWEBENCH,
            upstream_id=f"x-{licence}",
            origin_repo="org/repo",
            commit="c" * 40,
            licence=licence,
            files={"pkg/core.py": CORE, "pkg/util.py": UTIL},
            bugs=[
                Bug(
                    id="b1",
                    file="pkg/core.py",
                    lines=(50, 52),
                    category=BugCategory.BOUNDARY,
                    mechanism="SECRET_MECHANISM_TEXT off by one.",
                    fix_diff="--- a\n+++ b\n",
                )
            ],
            tests={"test_patch.diff": "SECRET_TEST_PATCH\n"},
        ),
    )
    return pub.meta.problem_id, pub.meta.version


class Env:
    def __init__(self, tmp_path: Path, engine: AsyncEngine) -> None:
        self.problems = tmp_path / "problems"
        self.engine = engine
        self.local = FakeBackend("fake-qwen")
        self.remote = FakeBackend("fake-gemini")
        self.settings = Settings(_env_file=None, max_question_chars=300)
        self.proxy = Proxy(
            settings=self.settings,
            counter=CharCounter(),
            local=self.local,
            realistic=self.remote,
            store=ProblemStore(self.problems),
        )
        self._n = 0

    async def session(
        self,
        mode: AssistantMode = AssistantMode.CONSTRAINED,
        ctx_cap: int = 100_000,
        q_budget: int = 12,
        licence: str = "BSD-3-Clause",
    ) -> SessionRow:
        pid, version = _publish(self.problems, licence)
        self._n += 1
        row = SessionRow(
            id=f"s{self._n}",
            problem_id=pid,
            problem_version=version,
            mode=mode,
            ctx_cap=ctx_cap,
            q_budget=q_budget,
        )
        async with AsyncSession(self.engine, expire_on_commit=False) as db:
            from corpus.publish import scan

            for p in scan(self.problems):
                await db.merge(index_row(p))
            db.add(row)
            await db.commit()
        return row

    async def ask(self, session: SessionRow, **kw: object) -> AskResult:
        req = AskRequest(**{"question": "What does this do?", **kw})
        async with AsyncSession(self.engine, expire_on_commit=False) as db:
            return await self.proxy.ask(db, session, req)

    async def queries(self, session: SessionRow) -> list[QueryRow]:
        async with AsyncSession(self.engine) as db:
            stmt = select(QueryRow).where(QueryRow.session_id == session.id)
            return list((await db.exec(stmt.order_by(col(QueryRow.seq)))).all())


@pytest.fixture
async def env(tmp_path: Path) -> AsyncIterator[Env]:
    engine = make_engine(f"sqlite+aiosqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    await init_db(engine)
    yield Env(tmp_path, engine)
    await engine.dispose()


SEL = {"file": "pkg/core.py", "line_from": 50, "line_to": 52}


# ---- Constrained mode: refusal paths (invariant 3) ----


@pytest.mark.parametrize(
    "selection",
    [{}, {"file": "pkg/core.py"}, {"file": "pkg/core.py", "line_from": 3}, {"line_from": 1}],
)
async def test_refuses_without_selection(env: Env, selection: dict[str, object]) -> None:
    s = await env.session()
    res = await env.ask(s, **selection)
    assert res.refused and res.reason is RefusalReason.NO_SELECTION
    assert env.local.calls == []


@pytest.mark.parametrize(
    "selection",
    [
        {"file": "pkg/missing.py", "line_from": 1, "line_to": 2},
        {"file": "pkg/core.py", "line_from": 199, "line_to": 201},
        {"file": "pkg/core.py", "line_from": 10, "line_to": 9},
        {"file": "../answer.json", "line_from": 1, "line_to": 2},
        {"file": "../tests/test_patch.diff", "line_from": 1, "line_to": 1},
    ],
)
async def test_refuses_invalid_selection(env: Env, selection: dict[str, object]) -> None:
    s = await env.session()
    res = await env.ask(s, **selection)
    assert res.reason is RefusalReason.INVALID_SELECTION
    assert env.local.calls == []


async def test_refuses_over_ctx_cap_with_exact_count(env: Env) -> None:
    s = await env.session(ctx_cap=env.proxy.constrained_overhead + 10)
    res = await env.ask(s, **SEL)
    assert res.reason is RefusalReason.OVER_CTX_CAP
    assert res.tokens is not None and res.tokens > s.ctx_cap
    assert env.local.calls == []


async def test_cap_counts_the_question_too(env: Env) -> None:
    s = await env.session()
    fits = await env.ask(s, **SEL)
    cap = fits.tokens
    assert cap is not None
    s2 = await env.session(ctx_cap=cap)
    assert not (await env.ask(s2, **SEL)).refused
    longer = await env.ask(s2, **SEL, question="What does this do? Explain in detail.")
    assert longer.reason is RefusalReason.OVER_CTX_CAP


async def test_refuses_overlong_question(env: Env) -> None:
    s = await env.session()
    res = await env.ask(s, **SEL, question="x" * 301)
    assert res.reason is RefusalReason.QUESTION_TOO_LONG


async def test_refuses_when_budget_exhausted(env: Env) -> None:
    s = await env.session(q_budget=2)
    for _ in range(2):
        assert not (await env.ask(s, **SEL)).refused
    res = await env.ask(s, **SEL)
    assert res.reason is RefusalReason.BUDGET_EXHAUSTED
    assert res.questions_used == 2
    assert len(env.local.calls) == 2


async def test_check_order_selection_then_cap_then_budget(env: Env) -> None:
    s = await env.session(ctx_cap=1, q_budget=0)
    assert (await env.ask(s)).reason is RefusalReason.NO_SELECTION
    assert (await env.ask(s, **SEL)).reason is RefusalReason.OVER_CTX_CAP
    s2 = await env.session(q_budget=0)
    assert (await env.ask(s2, **SEL)).reason is RefusalReason.BUDGET_EXHAUSTED


async def test_refusals_cost_no_budget_but_are_logged(env: Env) -> None:
    s = await env.session(q_budget=1)
    await env.ask(s)  # no selection
    await env.ask(s, file="pkg/core.py", line_from=500, line_to=501)  # invalid
    ok = await env.ask(s, **SEL)
    assert not ok.refused and ok.questions_used == 1
    rows = await env.queries(s)
    assert [r.refused_reason for r in rows] == ["no_selection", "invalid_selection", None]
    assert [r.seq for r in rows] == [1, 2, 3]


async def test_backend_failure_is_logged_refusal_without_cost(env: Env) -> None:
    s = await env.session(q_budget=1)
    env.local.fail = True
    res = await env.ask(s, **SEL)
    assert res.reason is RefusalReason.BACKEND_ERROR and res.questions_used == 0
    env.local.fail = False
    assert not (await env.ask(s, **SEL)).refused
    [failed, _] = await env.queries(s)
    assert failed.refused_reason == "backend_error"
    assert failed.latency_ms is not None


# ---- Constrained mode: only the selection is sent (invariant 4) ----


async def test_sends_only_selected_lines(env: Env) -> None:
    s = await env.session()
    await env.ask(s, **SEL)
    [[system, user]] = env.local.calls
    assert system.content == SYSTEM_CONSTRAINED
    sent = system.content + user.content
    for n in (50, 51, 52):
        assert f"core_line_{n} = {n}" in sent
    for n in (49, 53, 1, 200):
        assert f"core_line_{n} " not in sent
    assert "util_line" not in sent  # no other files
    for leaked in ("pkg/core.py", "org/repo", "BSD", "SECRET", "P-0001"):
        assert leaked not in sent  # no path, metadata or answer data
    assert "50 | core_line_50" in user.content


def test_system_prompts_never_mention_bugs_or_interviews() -> None:
    for prompt in (SYSTEM_CONSTRAINED, SYSTEM_REALISTIC):
        lowered = prompt.lower()
        for word in ("bug", "interview", "defect", "error", "flaw", "mistake", "test"):
            assert word not in lowered


# ---- Logging (invariant 6) ----


async def test_every_exchange_is_logged_with_details(env: Env) -> None:
    s = await env.session()
    await env.ask(s, **SEL, question="Why 51?")
    [row] = await env.queries(s)
    assert (row.file, row.line_from, row.line_to) == ("pkg/core.py", 50, 52)
    assert row.question == "Why 51?"
    assert row.reply == "reply from fake-qwen"
    assert row.model == "fake-qwen"
    assert row.tokens is not None and row.tokens > 0
    assert row.latency_ms is not None
    assert row.refused_reason is None


# ---- Realistic mode ----


async def test_realistic_sends_whole_file_and_has_no_budget(env: Env) -> None:
    s = await env.session(mode=AssistantMode.REALISTIC, q_budget=0, ctx_cap=1)
    res = await env.ask(s, **SEL)
    assert not res.refused and res.q_budget is None and res.ctx_cap is None
    [[system, user]] = env.remote.calls
    assert system.content == SYSTEM_REALISTIC
    assert "core_line_1 = 1" in user.content and "core_line_200 = 200" in user.content
    assert "util_line" not in user.content
    assert "lines 50-52 of `pkg/core.py`" in user.content
    assert env.local.calls == []
    [row] = await env.queries(s)
    assert row.model == "fake-gemini"


async def test_realistic_without_selection_sends_whole_problem(env: Env) -> None:
    s = await env.session(mode=AssistantMode.REALISTIC)
    await env.ask(s)
    [[_, user]] = env.remote.calls
    assert "core_line_200" in user.content and "util_line_160" in user.content
    assert "SECRET" not in user.content  # answer.json and tests/ never sent


async def test_realistic_refuses_non_allowlisted_licence(env: Env) -> None:
    """Invariant 7: only allowlisted open-source code goes to Gemini."""
    s = await env.session(mode=AssistantMode.REALISTIC, licence="GPL-3.0")
    res = await env.ask(s, **SEL)
    assert res.reason is RefusalReason.LICENCE_NOT_ALLOWED
    assert env.remote.calls == []
    assert len(await env.queries(s)) == 1


async def test_realistic_unconfigured_is_logged_refusal(env: Env) -> None:
    env.proxy.realistic = None
    s = await env.session(mode=AssistantMode.REALISTIC)
    res = await env.ask(s, **SEL)
    assert res.reason is RefusalReason.BACKEND_ERROR
    assert len(await env.queries(s)) == 1


# ---- HTTP route ----


@pytest.fixture
async def client(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db.sqlite"))
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_proxy] = lambda: env.proxy
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            yield c
    get_settings.cache_clear()


async def test_route_returns_refusal_as_200(env: Env, client: httpx.AsyncClient) -> None:
    s = await env.session()
    resp = await client.post(f"/api/sessions/{s.id}/ask", json={"question": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["refused"] is True and body["reason"] == "no_selection"


async def test_route_answers(env: Env, client: httpx.AsyncClient) -> None:
    s = await env.session()
    resp = await client.post(f"/api/sessions/{s.id}/ask", json={**SEL, "question": "hi"})
    body = resp.json()
    assert body["refused"] is False
    assert body["reply"] == "reply from fake-qwen"
    assert body["questions_used"] == 1 and body["q_budget"] == 12


async def test_route_unknown_session_404(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/sessions/nope/ask", json={"question": "hi"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "session_not_found"


async def test_route_submitted_session_409(env: Env, client: httpx.AsyncClient) -> None:
    s = await env.session()
    async with AsyncSession(env.engine) as db:
        row = await db.get(SessionRow, s.id)
        assert row is not None
        row.submitted_at = datetime.now(UTC)
        db.add(row)
        await db.commit()
    resp = await client.post(f"/api/sessions/{s.id}/ask", json={**SEL, "question": "hi"})
    assert resp.status_code == 409
    assert env.local.calls == []


async def test_route_rejects_empty_question(env: Env, client: httpx.AsyncClient) -> None:
    s = await env.session()
    resp = await client.post(f"/api/sessions/{s.id}/ask", json={**SEL, "question": ""})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


# ---- Wiring ----


async def test_build_proxy_uses_config_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.deps
    from api.backends.gemini import GeminiBackend
    from api.backends.ollama import OllamaBackend

    monkeypatch.setattr(api.deps, "HFTokenCounter", lambda name: CharCounter())
    plain = await api.deps.build_proxy(
        Settings(_env_file=None, local_model="cfg-local")  # type: ignore[call-arg]
    )
    assert isinstance(plain.local, OllamaBackend) and plain.local.model == "cfg-local"
    assert plain.realistic is None  # no key -> Realistic mode refuses, never guesses a model
    full = await api.deps.build_proxy(
        Settings(_env_file=None, gemini_api_key="k", realistic_model="cfg-remote")  # type: ignore[call-arg]
    )
    assert isinstance(full.realistic, GeminiBackend) and full.realistic.model == "cfg-remote"
    await plain.local.aclose()
    assert isinstance(full.local, OllamaBackend)
    await full.local.aclose()
