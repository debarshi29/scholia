from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db import (
    CategoryStatRow,
    ProblemRow,
    QueryRow,
    SessionRow,
    init_db,
    make_engine,
)
from schema import AssistantMode, BugCategory, Source

pytestmark = pytest.mark.anyio


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    await init_db(eng)
    yield eng
    await eng.dispose()


def _problem(version: int = 1) -> ProblemRow:
    return ProblemRow(
        id="P-0001",
        version=version,
        tier=0,
        source=Source.SWEBENCH,
        files=["worker.py"],
        lines=320,
        categories=[BugCategory.CONCURRENCY],
    )


def _session(version: int = 1) -> SessionRow:
    return SessionRow(
        id="s1",
        problem_id="P-0001",
        problem_version=version,
        mode=AssistantMode.CONSTRAINED,
        ctx_cap=3072,
        q_budget=12,
    )


async def test_all_spec_tables_exist(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
    assert names == {
        "problems",
        "sessions",
        "queries",
        "findings",
        "outcomes",
        "claim_audits",
        "category_stats",
        "patches",
        "profiles",
        "profile_stats",
        "fix_results",
    }


async def test_problem_versions_coexist(engine: AsyncEngine) -> None:
    """Invariant 8: a fix publishes a new version alongside the old one."""
    async with AsyncSession(engine) as db:
        db.add(_problem(1))
        db.add(_problem(2))
        await db.commit()
        rows = (await db.exec(select(ProblemRow).where(ProblemRow.id == "P-0001"))).all()
    assert sorted(r.version for r in rows) == [1, 2]
    assert rows[0].categories == [BugCategory.CONCURRENCY]


async def test_session_must_reference_existing_problem_version(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        db.add(_problem(1))
        await db.commit()
        db.add(_session(version=2))
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_query_seq_unique_per_session(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        db.add(_problem(1))
        db.add(_session())
        await db.commit()
        db.add(QueryRow(session_id="s1", seq=1, question="q", model="m", refused_reason="x"))
        db.add(QueryRow(session_id="s1", seq=1, question="q2", model="m"))
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_category_stats_roundtrip(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        db.add(CategoryStatRow(category=BugCategory.BOUNDARY, attempts=3, misses=1))
        await db.commit()
        row = await db.get(CategoryStatRow, BugCategory.BOUNDARY)
    assert row is not None
    assert (row.attempts, row.misses) == (3, 1)
