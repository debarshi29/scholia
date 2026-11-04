"""SQLModel engine and tables (CLAUDE.md §6). One SQLite file: ``data/scholia.db``.

Problems are immutable once published (invariant 8), so ``problems`` is keyed by
``(id, version)`` and sessions reference that pair.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import JSON, Column, ForeignKeyConstraint, UniqueConstraint, event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from schema import AssistantMode, BugCategory, ClaimVerdict, OutcomeStatus, Source


def utcnow() -> datetime:
    return datetime.now(UTC)


class ProblemRow(SQLModel, table=True):
    __tablename__ = "problems"

    id: str = Field(primary_key=True)
    version: int = Field(primary_key=True, ge=1)
    tier: int
    source: Source
    files: list[str] = Field(sa_column=Column(JSON, nullable=False))
    lines: int
    categories: list[BugCategory] = Field(sa_column=Column(JSON, nullable=False))
    published_at: datetime = Field(default_factory=utcnow)


class SessionRow(SQLModel, table=True):
    __tablename__ = "sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["problem_id", "problem_version"], ["problems.id", "problems.version"]
        ),
    )

    id: str = Field(primary_key=True)
    problem_id: str = Field(index=True)
    problem_version: int
    mode: AssistantMode
    ctx_cap: int
    q_budget: int
    started_at: datetime = Field(default_factory=utcnow)
    submitted_at: datetime | None = None
    overtime: bool = False


class QueryRow(SQLModel, table=True):
    """One assistant exchange, including refusals (invariant 6)."""

    __tablename__ = "queries"
    __table_args__ = (UniqueConstraint("session_id", "seq"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    seq: int
    file: str | None = None
    line_from: int | None = None
    line_to: int | None = None
    tokens: int | None = None
    question: str
    reply: str | None = None
    model: str
    latency_ms: int | None = None
    refused_reason: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class FindingRow(SQLModel, table=True):
    __tablename__ = "findings"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    file: str
    line_from: int
    line_to: int
    category: BugCategory
    explanation: str
    fix: str = ""


class OutcomeRow(SQLModel, table=True):
    """Per-bug / per-extra-finding grading result. Judge scores are null when ungraded."""

    __tablename__ = "outcomes"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    bug_id: str | None = None
    finding_id: int | None = Field(default=None, foreign_key="findings.id")
    status: OutcomeStatus
    assisted: bool = False
    judge_mechanism: int | None = Field(default=None, ge=0, le=2)
    judge_fix: int | None = Field(default=None, ge=0, le=2)
    prompt_version: str | None = None


class ClaimAuditRow(SQLModel, table=True):
    __tablename__ = "claim_audits"

    query_id: int = Field(primary_key=True, foreign_key="queries.id")
    verdict: ClaimVerdict
    relied_on: bool = False
    rationale: str = ""
    prompt_version: str | None = None


class CategoryStatRow(SQLModel, table=True):
    __tablename__ = "category_stats"

    category: BugCategory = Field(primary_key=True)
    attempts: int = Field(default=0, ge=0)
    misses: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=utcnow)


def _enable_sqlite_fks(dbapi_conn: Any, _record: Any) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url: str) -> AsyncEngine:
    """Async engine over aiosqlite. ``url`` must use the ``sqlite+aiosqlite://`` scheme."""
    engine = create_async_engine(url)
    event.listen(engine.sync_engine, "connect", _enable_sqlite_fks)
    return engine


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def session_scope(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Yield a session that keeps loaded attributes after commit (no lazy reloads under async)."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, on the engine created at startup."""
    async for session in session_scope(request.app.state.engine):
        yield session
