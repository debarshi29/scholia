"""Session API: library data, the weighted picker, the server-side clock and report intake.

Nothing here reads ``answer.json`` or ``tests/`` (invariant 1). The only answer-derived
datum this module touches is ``ProblemRow.categories``, used server-side by the picker
and never returned to the client.
"""

import random
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.config import Settings, get_settings
from api.db import (
    CategoryStatRow,
    FindingRow,
    OutcomeRow,
    ProblemRow,
    QueryRow,
    SessionRow,
    as_utc,
    get_db,
)
from api.deps import get_grader, get_proxy, get_store
from api.errors import ApiError
from api.grader.run import Grader
from api.problems import ProblemFileError, ProblemStore
from api.proxy import (
    AskRequest,
    AskResult,
    MeasureRequest,
    MeasureResult,
    Proxy,
    RefusalReason,
    questions_used,
)
from schema import AssistantMode, BugCategory, OutcomeStatus, Report, Source

router = APIRouter(prefix="/api", tags=["sessions"])

Db = Annotated[AsyncSession, Depends(get_db)]
Store = Annotated[ProblemStore, Depends(get_store)]
Config = Annotated[Settings, Depends(get_settings)]

EXPLORATION_FLOOR = 0.1
"""Base weight of every problem, so categories with no misses (or no data) still come up."""
MAX_FINDINGS = 50


def now() -> datetime:
    """The server clock (invariant 5). Tests replace this function."""
    return datetime.now(UTC)


# ---------- picker ----------


def miss_rates(stats: list[CategoryStatRow]) -> dict[BugCategory, float]:
    return {s.category: s.misses / s.attempts for s in stats if s.attempts > 0}


def problem_weight(categories: list[BugCategory], rates: dict[BugCategory, float]) -> float:
    return EXPLORATION_FLOOR + sum(rates.get(BugCategory(c), 0.0) for c in categories)


def pick_problem(
    problems: list[ProblemRow],
    attempted: set[str],
    rates: dict[BugCategory, float],
    rng: random.Random,
) -> ProblemRow | None:
    """Weighted random choice among unattempted problems (all problems once none are left)."""
    pool = [p for p in problems if p.id not in attempted] or problems
    if not pool:
        return None
    weights = [problem_weight(p.categories, rates) for p in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


# ---------- response models ----------


class ProblemCard(BaseModel):
    """A library entry. Deliberately has no category, upstream id or commit: with one bug
    per problem, any of those would point at the answer."""

    id: str
    version: int
    tier: int
    source: Source
    origin_repo: str
    licence: str
    files: list[str]
    lines: int
    attempts: int
    last_attempt_at: datetime | None
    best_found: int | None
    """Most key bugs matched in one graded attempt (``None`` before the first one)."""
    best_bugs: int | None
    best_seconds: int | None


class CategoryStat(BaseModel):
    category: BugCategory
    attempts: int
    misses: int
    miss_rate: float | None
    """``None`` until the category has been attempted."""


class ModeInfo(BaseModel):
    mode: AssistantMode
    available: bool
    model: str


class LibrarySettings(BaseModel):
    default_ctx_cap: int
    default_q_budget: int
    session_minutes: int
    max_question_chars: int
    modes: list[ModeInfo]


class SessionCreate(BaseModel):
    problem_id: str | None = None
    source: Source | None = None
    """Restricts the picker; ignored when ``problem_id`` is given."""
    mode: AssistantMode = AssistantMode.CONSTRAINED
    ctx_cap: int | None = Field(default=None, gt=0, le=32768)
    q_budget: int | None = Field(default=None, ge=0, le=200)


class SourceFile(BaseModel):
    path: str
    content: str


class ThreadItem(BaseModel):
    query_id: int
    seq: int
    file: str | None
    line_from: int | None
    line_to: int | None
    question: str
    refused: bool
    reason: RefusalReason | None
    reply: str | None
    tokens: int | None
    model: str


class SessionSummary(BaseModel):
    id: str
    problem_id: str
    problem_version: int
    mode: AssistantMode
    started_at: datetime
    submitted_at: datetime | None
    overtime: bool
    graded: bool
    grade_error: str | None


class SessionView(SessionSummary):
    ctx_cap: int
    q_budget: int
    session_seconds: int
    seconds_left: int
    """Display only; the server decides ``overtime`` at submit."""
    questions_used: int
    origin_repo: str
    model: str
    """The model this session's assistant uses."""
    files: list[SourceFile]
    thread: list[ThreadItem]


class SubmitResult(BaseModel):
    submitted_at: datetime
    overtime: bool
    findings: int


# ---------- helpers ----------


def summary(s: SessionRow) -> SessionSummary:
    return SessionSummary(
        id=s.id,
        problem_id=s.problem_id,
        problem_version=s.problem_version,
        mode=s.mode,
        started_at=as_utc(s.started_at),
        submitted_at=as_utc(s.submitted_at) if s.submitted_at else None,
        overtime=s.overtime,
        graded=s.graded_at is not None,
        grade_error=s.grade_error,
    )


def elapsed_seconds(session: SessionRow, at: datetime) -> float:
    return (at - as_utc(session.started_at)).total_seconds()


async def load_session(db: AsyncSession, session_id: str) -> SessionRow:
    session = await db.get(SessionRow, session_id)
    if session is None:
        raise ApiError(404, "session_not_found", "Session not found")
    return session


async def live_session(db: AsyncSession, session_id: str) -> SessionRow:
    session = await load_session(db, session_id)
    if session.submitted_at is not None:
        raise ApiError(409, "session_submitted", "Session already submitted")
    return session


async def latest_problems(db: AsyncSession) -> list[ProblemRow]:
    rows = (await db.exec(select(ProblemRow).order_by(col(ProblemRow.id)))).all()
    latest: dict[str, ProblemRow] = {}
    for row in rows:
        if row.id not in latest or row.version > latest[row.id].version:
            latest[row.id] = row
    return list(latest.values())


def _thread_item(q: QueryRow) -> ThreadItem:
    assert q.id is not None
    reason = RefusalReason(q.refused_reason) if q.refused_reason else None
    return ThreadItem(
        query_id=q.id,
        seq=q.seq,
        file=q.file,
        line_from=q.line_from,
        line_to=q.line_to,
        question=q.question,
        refused=reason is not None,
        reason=reason,
        reply=None if reason else q.reply,
        tokens=q.tokens,
        model=q.model,
    )


# ---------- library ----------


async def best_results(db: AsyncSession) -> dict[str, tuple[int, int, int]]:
    """Per problem: ``(bugs matched, key bugs, seconds used)`` of the best graded attempt.
    More bugs wins; ties go to the faster attempt."""
    matched: dict[str, list[int]] = {}
    stmt = select(OutcomeRow.session_id, OutcomeRow.status).where(
        col(OutcomeRow.bug_id).is_not(None)
    )
    for session_id, status in (await db.exec(stmt)).all():
        counts = matched.setdefault(session_id, [0, 0])
        counts[0] += status in (OutcomeStatus.FOUND, OutcomeStatus.PARTIAL)
        counts[1] += 1
    best: dict[str, tuple[int, int, int]] = {}
    graded = select(SessionRow).where(col(SessionRow.graded_at).is_not(None))
    for s in (await db.exec(graded)).all():
        if s.id not in matched or s.submitted_at is None:
            continue
        found, bugs = matched[s.id]
        seconds = round(elapsed_seconds(s, as_utc(s.submitted_at)))
        current = best.get(s.problem_id)
        if current is None or (found, -seconds) > (current[0], -current[2]):
            best[s.problem_id] = (found, bugs, seconds)
    return best


def mix_projects(cards: list[ProblemCard], ranks: list[tuple[bool, float]]) -> list[ProblemCard]:
    """Within each run of equally ranked cards, take one project in turn, so the list does
    not open with twenty files from the same repo. The rank order itself is unchanged."""
    out: list[ProblemCard] = []
    start = 0
    while start < len(cards):
        end = start
        while end < len(cards) and ranks[end] == ranks[start]:
            end += 1
        by_repo: dict[str, list[ProblemCard]] = {}
        for card in cards[start:end]:
            by_repo.setdefault(card.origin_repo, []).append(card)
        for i in range(max(len(group) for group in by_repo.values())):
            out.extend(group[i] for group in by_repo.values() if i < len(group))
        start = end
    return out


@router.get("/problems", response_model=list[ProblemCard])
async def list_problems(db: Db, store: Store) -> list[ProblemCard]:
    stmt = select(SessionRow.problem_id, func.count(), func.max(SessionRow.started_at)).group_by(
        col(SessionRow.problem_id)
    )
    attempts = {pid: (n, last) for pid, n, last in (await db.exec(stmt)).all()}
    best = await best_results(db)
    rates = miss_rates(list((await db.exec(select(CategoryStatRow))).all()))
    # Not attempted first, then by picker weight: weak spots come first. The weight
    # itself and the categories behind it are never sent to the client.
    ordered = sorted(
        await latest_problems(db),
        key=lambda p: (p.id in attempts, -problem_weight(p.categories, rates), p.id),
    )
    cards: list[ProblemCard] = []
    ranks: list[tuple[bool, float]] = []
    for p in ordered:
        try:
            meta = await store.meta(p.id, p.version)
        except ProblemFileError:
            continue  # indexed but missing on disk: not startable, so not listed
        n, last = attempts.get(p.id, (0, None))
        found, bugs, seconds = best.get(p.id, (None, None, None))
        ranks.append((p.id in attempts, problem_weight(p.categories, rates)))
        cards.append(
            ProblemCard(
                id=p.id,
                version=p.version,
                tier=p.tier,
                source=p.source,
                origin_repo=meta.origin_repo,
                licence=meta.licence,
                files=p.files,
                lines=p.lines,
                attempts=n,
                last_attempt_at=as_utc(last) if last else None,
                best_found=found,
                best_bugs=bugs,
                best_seconds=seconds,
            )
        )
    return mix_projects(cards, ranks)


@router.get("/stats", response_model=list[CategoryStat])
async def category_stats(db: Db) -> list[CategoryStat]:
    rows = {r.category: r for r in (await db.exec(select(CategoryStatRow))).all()}
    out: list[CategoryStat] = []
    for category in BugCategory:
        row = rows.get(category)
        attempts = row.attempts if row else 0
        misses = row.misses if row else 0
        out.append(
            CategoryStat(
                category=category,
                attempts=attempts,
                misses=misses,
                miss_rate=misses / attempts if attempts else None,
            )
        )
    return out


@router.get("/settings", response_model=LibrarySettings)
async def library_settings(settings: Config) -> LibrarySettings:
    realistic_ok = settings.gemini_api_key is not None and bool(settings.realistic_model)
    return LibrarySettings(
        default_ctx_cap=settings.default_ctx_cap,
        default_q_budget=settings.default_q_budget,
        session_minutes=settings.session_minutes,
        max_question_chars=settings.max_question_chars,
        modes=[
            ModeInfo(mode=AssistantMode.CONSTRAINED, available=True, model=settings.local_model),
            ModeInfo(
                mode=AssistantMode.REALISTIC,
                available=realistic_ok,
                model=settings.realistic_model,
            ),
        ],
    )


# ---------- sessions ----------


async def _view(
    db: AsyncSession, store: ProblemStore, settings: Settings, session: SessionRow
) -> SessionView:
    try:
        paths = await store.src_files(session.problem_id, session.problem_version)
        files = [
            SourceFile(
                path=p,
                content=await store.read_src(session.problem_id, session.problem_version, p),
            )
            for p in paths
        ]
    except ProblemFileError as exc:
        raise ApiError(410, "problem_files_missing", str(exc)) from exc
    queries = (
        await db.exec(
            select(QueryRow).where(QueryRow.session_id == session.id).order_by(col(QueryRow.seq))
        )
    ).all()
    meta = await store.meta(session.problem_id, session.problem_version)
    constrained = session.mode == AssistantMode.CONSTRAINED
    total = settings.session_minutes * 60
    end = as_utc(session.submitted_at) if session.submitted_at else now()
    return SessionView(
        **summary(session).model_dump(),
        ctx_cap=session.ctx_cap,
        q_budget=session.q_budget,
        session_seconds=total,
        seconds_left=max(0, round(total - elapsed_seconds(session, end))),
        questions_used=await questions_used(db, session.id),
        origin_repo=meta.origin_repo,
        model=settings.local_model if constrained else settings.realistic_model,
        files=files,
        thread=[_thread_item(q) for q in queries],
    )


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(db: Db) -> list[SessionSummary]:
    rows = (await db.exec(select(SessionRow).order_by(col(SessionRow.started_at).desc()))).all()
    return [summary(r) for r in rows]


@router.post("/sessions", response_model=SessionView, status_code=201)
async def create_session(req: SessionCreate, db: Db, store: Store, settings: Config) -> SessionView:
    problems = await latest_problems(db)
    if req.problem_id is not None:
        problem = next((p for p in problems if p.id == req.problem_id), None)
        if problem is None:
            raise ApiError(404, "problem_not_found", f"No problem {req.problem_id}")
    else:
        pool = [p for p in problems if req.source is None or p.source == req.source]
        attempted = set((await db.exec(select(SessionRow.problem_id).distinct())).all())
        stats = list((await db.exec(select(CategoryStatRow))).all())
        picked = pick_problem(pool, attempted, miss_rates(stats), random.Random())
        if picked is None:
            raise ApiError(409, "no_problems", "No published problems; run corpus.build first")
        problem = picked
    if req.mode == AssistantMode.REALISTIC and not (
        settings.gemini_api_key is not None and settings.realistic_model
    ):
        raise ApiError(409, "realistic_unavailable", "Realistic mode needs a Gemini key and model")
    session = SessionRow(
        id=uuid.uuid4().hex,
        problem_id=problem.id,
        problem_version=problem.version,
        mode=req.mode,
        ctx_cap=req.ctx_cap or settings.default_ctx_cap,
        q_budget=settings.default_q_budget if req.q_budget is None else req.q_budget,
        started_at=now(),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return await _view(db, store, settings, session)


@router.get("/sessions/{session_id}", response_model=SessionView)
async def get_session(session_id: str, db: Db, store: Store, settings: Config) -> SessionView:
    return await _view(db, store, settings, await load_session(db, session_id))


@router.post("/sessions/{session_id}/ask", response_model=AskResult)
async def ask(
    session_id: str, req: AskRequest, db: Db, proxy: Annotated[Proxy, Depends(get_proxy)]
) -> AskResult:
    """Ask the assistant. Refusals are 200 responses with ``refused: true``."""
    return await proxy.ask(db, await live_session(db, session_id), req)


@router.post("/sessions/{session_id}/measure", response_model=MeasureResult)
async def measure(
    session_id: str, req: MeasureRequest, db: Db, proxy: Annotated[Proxy, Depends(get_proxy)]
) -> MeasureResult:
    """Token cost of a selection for the context bar. Reaches no model and costs no budget."""
    return await proxy.measure(await live_session(db, session_id), req)


async def freeze_report(
    db: AsyncSession, store: ProblemStore, settings: Settings, session: SessionRow, report: Report
) -> SubmitResult:
    """Validate and store the report, stop the clock and flag overtime."""
    if len(report.findings) > MAX_FINDINGS:
        raise ApiError(422, "too_many_findings", f"At most {MAX_FINDINGS} findings")
    lengths: dict[str, int] = {}
    for f in report.findings:
        if f.file not in lengths:
            try:
                lengths[f.file] = len(
                    await store.read_src_lines(session.problem_id, session.problem_version, f.file)
                )
            except ProblemFileError as exc:
                raise ApiError(422, "invalid_finding", f"Unknown file {f.file!r}") from exc
        if f.line_to > lengths[f.file]:
            raise ApiError(
                422, "invalid_finding", f"{f.file} has {lengths[f.file]} lines, got {f.line_to}"
            )
    submitted = now()
    session.submitted_at = submitted
    session.overtime = elapsed_seconds(session, submitted) > settings.session_minutes * 60
    session.design_notes = report.design_notes
    db.add(session)
    for f in report.findings:
        db.add(FindingRow(session_id=session.id, **f.model_dump()))
    await db.commit()
    return SubmitResult(
        submitted_at=submitted, overtime=session.overtime, findings=len(report.findings)
    )


@router.post("/sessions/{session_id}/submit", response_model=SubmitResult)
async def submit(
    session_id: str,
    report: Report,
    db: Db,
    store: Store,
    settings: Config,
    background: BackgroundTasks,
    grader: Annotated[Grader, Depends(get_grader)],
) -> SubmitResult:
    """Freeze the report and grade it in the background. Late submissions are accepted
    and flagged ``overtime``."""
    session = await live_session(db, session_id)
    result = await freeze_report(db, store, settings, session, report)
    background.add_task(grader.grade, session.id)
    return result
