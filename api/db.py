"""SQLModel engine and tables (CLAUDE.md §6). One SQLite file: ``data/scholia.db``.

Problems are immutable once published (invariant 8), so ``problems`` is keyed by
``(id, version)`` and sessions reference that pair.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import JSON, Column, ForeignKeyConstraint, UniqueConstraint, event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import Field, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from schema import AssistantMode, BugCategory, ClaimVerdict, OutcomeStatus, Source


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; everything stored here is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


DEFAULT_PROFILE = "default"


class ProfileRow(SQLModel, table=True):
    """A local profile: a name, session defaults and (through ``profile_stats`` and
    ``sessions.profile_id``) its own history. There is no login: it is a way to keep
    several people's, or several goals', progress apart on one machine."""

    __tablename__ = "profiles"

    id: str = Field(primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=utcnow)
    default_mode: AssistantMode | None = None
    default_ctx_cap: int | None = Field(default=None, ge=256)
    default_q_budget: int | None = Field(default=None, ge=0)
    """``None`` means the server default from config."""


class ProfileStatRow(SQLModel, table=True):
    """Per-profile miss counts by category (replaces the single global ``category_stats``)."""

    __tablename__ = "profile_stats"

    profile_id: str = Field(foreign_key="profiles.id", primary_key=True)
    category: BugCategory = Field(primary_key=True)
    attempts: int = Field(default=0, ge=0)
    misses: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=utcnow)


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
    profile_id: str = Field(default=DEFAULT_PROFILE)
    ctx_cap: int
    q_budget: int
    started_at: datetime = Field(default_factory=utcnow)
    submitted_at: datetime | None = None
    overtime: bool = False
    design_notes: str = ""
    """The report's free-text design notes, frozen at submit."""
    graded_at: datetime | None = None
    grade_error: str | None = None
    """Set when grading crashed; the debrief stays unavailable until a regrade succeeds."""
    design_score: int | None = Field(default=None, ge=0, le=3)
    design_rationale: str = ""
    stats_delta: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    """Category stats before/after this session, written once by the tracker."""


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
    marked_valid: bool = False
    """The user's own verdict, after the debrief, that an extra finding is a fair point. It is a
    note: it never changes matching, scores or stats."""


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
    judge_notes: str = ""
    prompt_version: str | None = None


class PatchRow(SQLModel, table=True):
    """The user's edited copy of one file, frozen at submit, with its diff from the original."""

    __tablename__ = "patches"
    __table_args__ = (UniqueConstraint("session_id", "file"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    file: str
    content: str
    diff: str


class FixResultRow(SQLModel, table=True):
    """How the submitted fix did against one key bug."""

    __tablename__ = "fix_results"
    __table_args__ = (UniqueConstraint("session_id", "bug_id"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    bug_id: str
    submitted: bool = False
    """The bug's file was edited at all."""
    on_target: bool = False
    """The edit changed the bug's lines (deterministic, same tolerance as matching)."""
    syntax_error: str | None = None
    judge_fix: int | None = Field(default=None, ge=0, le=2)
    judge_notes: str = ""
    tests: str | None = None
    """``passed`` / ``failed`` / ``error`` where the problem has runnable tests, else null."""
    tests_detail: str = ""
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
        # ``create_all`` never alters a table that exists: add what later versions need.
        columns = {row[1] for row in (await conn.execute(text("PRAGMA table_info(sessions)")))}
        finding_columns = {
            row[1] for row in (await conn.execute(text("PRAGMA table_info(findings)")))
        }
        if "marked_valid" not in finding_columns:
            await conn.execute(
                text("ALTER TABLE findings ADD COLUMN marked_valid BOOLEAN NOT NULL DEFAULT 0")
            )
        if "profile_id" not in columns:
            await conn.execute(
                text(
                    "ALTER TABLE sessions ADD COLUMN profile_id TEXT NOT NULL "
                    f"DEFAULT '{DEFAULT_PROFILE}'"
                )
            )
        # The first start with profiles: everything so far belongs to the default profile.
        if (await conn.execute(text("SELECT count(*) FROM profiles"))).scalar_one() == 0:
            now = utcnow().isoformat(sep=" ")
            await conn.execute(
                text("INSERT INTO profiles (id, name, created_at) VALUES (:id, 'Default', :now)"),
                {"id": DEFAULT_PROFILE, "now": now},
            )
            await conn.execute(
                text(
                    "INSERT INTO profile_stats "
                    "(profile_id, category, attempts, misses, updated_at) "
                    "SELECT :id, category, attempts, misses, updated_at FROM category_stats"
                ),
                {"id": DEFAULT_PROFILE},
            )


async def session_scope(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Yield a session that keeps loaded attributes after commit (no lazy reloads under async)."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, on the engine created at startup."""
    async for session in session_scope(request.app.state.engine):
        yield session
