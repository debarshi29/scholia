"""Debrief API: the only place answer data is returned, and only after submit and grading."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.config import Settings, get_settings
from api.db import (
    ClaimAuditRow,
    FindingRow,
    FixResultRow,
    OutcomeRow,
    PatchRow,
    QueryRow,
    as_utc,
    get_db,
)
from api.deps import get_grader, get_store
from api.errors import ApiError
from api.grader.run import Grader, answered
from api.problems import ProblemStore
from api.sessions import SessionSummary, elapsed_seconds, load_session, summary
from corpus.publish import load_answer
from schema import AssistantMode, BugCategory, ClaimVerdict, OutcomeStatus, Severity, Source

router = APIRouter(prefix="/api/sessions", tags=["debrief"])

Db = Annotated[AsyncSession, Depends(get_db)]


class DebriefFinding(BaseModel):
    id: int
    file: str
    line_from: int
    line_to: int
    category: BugCategory
    explanation: str
    fix: str
    marked_valid: bool = False


class DebriefFix(BaseModel):
    """How the submitted code fix did against one key bug."""

    submitted: bool
    on_target: bool
    syntax_error: str | None
    judge_fix: int | None
    judge_notes: str
    tests: str | None
    tests_detail: str


class DebriefPatch(BaseModel):
    file: str
    diff: str


class DebriefBug(BaseModel):
    id: str
    file: str
    line_from: int
    line_to: int
    category: BugCategory
    severity: Severity
    mechanism: str
    fix_diff: str
    killing_test: str | None
    status: OutcomeStatus
    assisted: bool
    finding: DebriefFinding | None
    judge_mechanism: int | None
    judge_fix: int | None
    judge_notes: str
    fix: DebriefFix | None


class DebriefAudit(BaseModel):
    query_id: int
    seq: int
    file: str | None
    line_from: int | None
    line_to: int | None
    question: str
    reply: str
    model: str
    tokens: int | None
    verdict: ClaimVerdict | None
    """``None`` when the judge gave no valid label for this reply."""
    relied_on: bool
    rationale: str


class DebriefProblem(BaseModel):
    id: str
    version: int
    source: Source
    upstream_id: str
    origin_repo: str
    commit: str
    licence: str


class DebriefDesign(BaseModel):
    notes: str
    reference: list[str]
    score: int | None
    rationale: str


class DebriefTotals(BaseModel):
    bugs: int
    found: int
    partial: int
    missed: int
    ungraded: int
    extra: int
    assisted: int
    questions_used: int
    refusals: int
    wrong_claims: int
    relied_on_wrong: int
    seconds_used: int
    session_seconds: int
    q_budget: int | None
    """Constrained mode only."""


class StatDelta(BaseModel):
    category: BugCategory
    attempts_before: int
    misses_before: int
    attempts_after: int
    misses_after: int


class Debrief(BaseModel):
    session: SessionSummary
    problem: DebriefProblem
    totals: DebriefTotals
    bugs: list[DebriefBug]
    extras: list[DebriefFinding]
    patches: list[DebriefPatch]
    """Every file the user edited, as a diff from the buggy original."""
    audits: list[DebriefAudit]
    design: DebriefDesign
    stats_delta: list[StatDelta]
    judge_model: str | None


def _fix(row: FixResultRow | None) -> DebriefFix | None:
    if row is None:
        return None
    return DebriefFix(
        submitted=row.submitted,
        on_target=row.on_target,
        syntax_error=row.syntax_error,
        judge_fix=row.judge_fix,
        judge_notes=row.judge_notes,
        tests=row.tests,
        tests_detail=row.tests_detail,
    )


def _finding(row: FindingRow) -> DebriefFinding:
    assert row.id is not None
    return DebriefFinding(
        id=row.id,
        file=row.file,
        line_from=row.line_from,
        line_to=row.line_to,
        category=row.category,
        explanation=row.explanation,
        fix=row.fix,
        marked_valid=row.marked_valid,
    )


class ValidityRequest(BaseModel):
    valid: bool


@router.post("/{session_id}/findings/{finding_id}/validity", response_model=DebriefFinding)
async def mark_validity(
    session_id: str, finding_id: int, req: ValidityRequest, db: Db
) -> DebriefFinding:
    """Mark a finding that matched no key bug as a fair point (or take the mark back). It is
    the user's own note after the debrief: matching, scores and stats do not change."""
    session = await load_session(db, session_id)
    if session.submitted_at is None:
        raise ApiError(409, "not_submitted", "Submit the report first")
    finding = await db.get(FindingRow, finding_id)
    if finding is None or finding.session_id != session.id:
        raise ApiError(404, "finding_not_found", f"No finding {finding_id} in this session")
    outcome = (
        await db.exec(
            select(OutcomeRow).where(
                OutcomeRow.session_id == session.id, OutcomeRow.finding_id == finding_id
            )
        )
    ).first()
    if outcome is None or outcome.status is not OutcomeStatus.EXTRA:
        raise ApiError(409, "not_extra", "Only findings outside the answer key can be marked")
    finding.marked_valid = req.valid
    db.add(finding)
    await db.commit()
    return _finding(finding)


@router.get("/{session_id}/debrief", response_model=Debrief)
async def debrief(
    session_id: str,
    db: Db,
    store: Annotated[ProblemStore, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
    grader: Annotated[Grader, Depends(get_grader)],
) -> Debrief:
    session = await load_session(db, session_id)
    # Invariant 1: nothing below this point runs for a live session.
    if session.submitted_at is None:
        raise ApiError(409, "not_submitted", "Submit the report to see the debrief")
    if session.graded_at is None:
        if session.grade_error:
            raise ApiError(409, "grading_failed", session.grade_error)
        raise ApiError(409, "grading_pending", "Grading is still running")

    pid, version = session.problem_id, session.problem_version
    answer = await asyncio.to_thread(load_answer, settings.problems_dir, pid, version)
    meta = await store.meta(pid, version)
    findings = {
        f.id: f
        for f in (
            await db.exec(select(FindingRow).where(FindingRow.session_id == session_id))
        ).all()
    }
    outcomes = (
        await db.exec(
            select(OutcomeRow)
            .where(OutcomeRow.session_id == session_id)
            .order_by(col(OutcomeRow.id))
        )
    ).all()
    queries = (
        await db.exec(
            select(QueryRow).where(QueryRow.session_id == session_id).order_by(col(QueryRow.seq))
        )
    ).all()
    query_ids = [q.id for q in queries if q.id is not None]
    audits = {
        a.query_id: a
        for a in (
            await db.exec(select(ClaimAuditRow).where(col(ClaimAuditRow.query_id).in_(query_ids)))
        ).all()
    }

    by_bug = {o.bug_id: o for o in outcomes if o.bug_id is not None}
    fix_rows = (
        await db.exec(select(FixResultRow).where(FixResultRow.session_id == session_id))
    ).all()
    fixes = {r.bug_id: r for r in fix_rows}
    patch_rows = (
        await db.exec(
            select(PatchRow).where(PatchRow.session_id == session_id).order_by(col(PatchRow.file))
        )
    ).all()
    bugs: list[DebriefBug] = []
    for bug in answer.bugs:
        o = by_bug[bug.id]
        row = findings.get(o.finding_id) if o.finding_id is not None else None
        bugs.append(
            DebriefBug(
                id=bug.id,
                file=bug.file,
                line_from=bug.lines[0],
                line_to=bug.lines[1],
                category=bug.category,
                severity=bug.severity,
                mechanism=bug.mechanism,
                fix_diff=bug.fix_diff,
                killing_test=bug.killing_test,
                status=o.status,
                assisted=o.assisted,
                finding=_finding(row) if row else None,
                judge_mechanism=o.judge_mechanism,
                judge_fix=o.judge_fix,
                judge_notes=o.judge_notes,
                fix=_fix(fixes.get(bug.id)),
            )
        )
    extras = [
        _finding(findings[o.finding_id])
        for o in outcomes
        if o.status is OutcomeStatus.EXTRA and o.finding_id in findings
    ]
    audit_items: list[DebriefAudit] = []
    for q in queries:
        if not answered(q) or q.id is None or q.reply is None:
            continue
        a = audits.get(q.id)
        audit_items.append(
            DebriefAudit(
                query_id=q.id,
                seq=q.seq,
                file=q.file,
                line_from=q.line_from,
                line_to=q.line_to,
                question=q.question,
                reply=q.reply,
                model=q.model,
                tokens=q.tokens,
                verdict=a.verdict if a else None,
                relied_on=a.relied_on if a else False,
                rationale=a.rationale if a else "",
            )
        )

    def count(status: OutcomeStatus) -> int:
        return sum(o.status is status for o in outcomes)

    totals = DebriefTotals(
        bugs=len(answer.bugs),
        found=count(OutcomeStatus.FOUND),
        partial=count(OutcomeStatus.PARTIAL),
        missed=count(OutcomeStatus.MISSED),
        ungraded=count(OutcomeStatus.UNGRADED),
        extra=count(OutcomeStatus.EXTRA),
        assisted=sum(o.assisted for o in outcomes),
        questions_used=len(audit_items),
        refusals=sum(q.refused_reason is not None for q in queries),
        wrong_claims=sum(a.verdict is ClaimVerdict.WRONG for a in audit_items),
        relied_on_wrong=sum(a.relied_on for a in audit_items),
        seconds_used=round(elapsed_seconds(session, as_utc(session.submitted_at))),
        session_seconds=settings.session_minutes * 60,
        q_budget=session.q_budget if session.mode == AssistantMode.CONSTRAINED else None,
    )
    return Debrief(
        session=summary(session),
        problem=DebriefProblem(
            id=pid,
            version=version,
            source=meta.source,
            upstream_id=meta.upstream_id,
            origin_repo=meta.origin_repo,
            commit=meta.commit,
            licence=meta.licence,
        ),
        totals=totals,
        bugs=bugs,
        extras=extras,
        patches=[DebriefPatch(file=p.file, diff=p.diff) for p in patch_rows],
        audits=audit_items,
        design=DebriefDesign(
            notes=session.design_notes,
            reference=list(answer.design_notes),
            score=session.design_score,
            rationale=session.design_rationale,
        ),
        stats_delta=[StatDelta(**d) for d in session.stats_delta or []],
        judge_model=grader.judge.model,
    )


@router.post("/{session_id}/regrade", status_code=202)
async def regrade(
    session_id: str,
    db: Db,
    background: BackgroundTasks,
    grader: Annotated[Grader, Depends(get_grader)],
) -> dict[str, str]:
    """Run grading again, for example after the judge was unreachable. Matching and the
    category stats do not change; only judge scores and audit labels can."""
    session = await load_session(db, session_id)
    if session.submitted_at is None:
        raise ApiError(409, "not_submitted", "Only submitted sessions can be graded")
    session.graded_at = None
    session.grade_error = None
    db.add(session)
    await db.commit()
    background.add_task(grader.grade, session_id)
    return {"status": "grading"}
