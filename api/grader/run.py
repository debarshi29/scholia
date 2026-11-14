"""Grades one submitted session: match, judge, audit, tracker.

This is the only code that reads ``answer.json`` for a session, and it refuses to run
before ``submitted_at`` is set (invariant 1). Grading always finishes: a judge that is
down or returns bad output leaves ``ungraded`` scores, never an error or a guess.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.config import Settings
from api.db import (
    ClaimAuditRow,
    FindingRow,
    FixResultRow,
    OutcomeRow,
    PatchRow,
    QueryRow,
    SessionRow,
    utcnow,
)
from api.grader.audit import BugResult, QueryScope, is_assisted, label_claim, relied_on
from api.grader.fix import changed_ranges, python_syntax_error, touches_bug
from api.grader.judge import Judge
from api.grader.match import BugSpan, FindingSpan, Span, match
from api.problems import ProblemStore
from api.proxy import numbered
from api.tracker import apply_session
from corpus.filters import is_allowed_licence
from corpus.publish import load_answer
from schema import AnswerKey, Bug, Finding, OutcomeStatus

log = logging.getLogger(__name__)

CONTEXT_LINES = 10
NO_REFERENCE = "This problem has no reference design notes, so the notes were not scored."
NO_NOTES = "No design notes were written."
NO_SCORE = "The judge returned no valid score, so the notes are ungraded."


class GradingError(RuntimeError):
    pass


def to_finding(row: FindingRow) -> Finding:
    return Finding(
        file=row.file,
        line_from=row.line_from,
        line_to=row.line_to,
        category=row.category,
        explanation=row.explanation,
        fix=row.fix,
    )


def scope_of(q: QueryRow) -> QueryScope:
    return QueryScope(file=q.file, line_from=q.line_from, line_to=q.line_to)


def answered(q: QueryRow) -> bool:
    return q.refused_reason is None and bool(q.reply)


class Grader:
    def __init__(
        self, engine: AsyncEngine, settings: Settings, store: ProblemStore, judge: Judge
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.store = store
        self.judge = judge
        self._no_judge = Judge(None, judge.max_tokens)

    async def grade(self, session_id: str) -> None:
        """Background-task entry point. Never raises; a crash is stored on the session."""
        try:
            async with AsyncSession(self.engine, expire_on_commit=False) as db:
                await self._grade(db, session_id)
        except Exception as exc:
            log.exception("grading failed", extra={"session_id": session_id})
            async with AsyncSession(self.engine, expire_on_commit=False) as db:
                session = await db.get(SessionRow, session_id)
                if session is not None:
                    session.grade_error = f"{type(exc).__name__}: {exc}"[:500]
                    db.add(session)
                    await db.commit()

    async def _code(self, session: SessionRow, file: str, first: int, last: int) -> str:
        lines = await self.store.read_src_lines(session.problem_id, session.problem_version, file)
        a = max(1, first - CONTEXT_LINES)
        b = min(len(lines), last + CONTEXT_LINES)
        return numbered(lines[a - 1 : b], a)

    async def _shown(self, session: SessionRow, q: QueryRow) -> str:
        """The code a query put in front of the assistant."""
        pid, version = session.problem_id, session.problem_version
        if q.file is None:
            parts = []
            for path in await self.store.src_files(pid, version):
                lines = await self.store.read_src_lines(pid, version, path)
                parts.append(f"# file: {path}\n{numbered(lines, 1)}")
            return "\n\n".join(parts)
        lines = await self.store.read_src_lines(pid, version, q.file)
        if q.line_from is None or q.line_to is None:
            return numbered(lines, 1)
        return numbered(lines[q.line_from - 1 : q.line_to], q.line_from)

    async def _grade(self, db: AsyncSession, session_id: str) -> None:
        session = await db.get(SessionRow, session_id)
        if session is None:
            raise GradingError(f"no session {session_id}")
        if session.submitted_at is None:
            raise GradingError("session is not submitted; the answer key stays closed")
        pid, version = session.problem_id, session.problem_version
        answer: AnswerKey = await asyncio.to_thread(
            load_answer, self.settings.problems_dir, pid, version
        )
        meta = await self.store.meta(pid, version)
        # Invariant 7: only allowlisted open-source code is sent to Gemini.
        judge = self.judge if is_allowed_licence(meta.licence) else self._no_judge

        findings = list(
            (
                await db.exec(
                    select(FindingRow)
                    .where(FindingRow.session_id == session_id)
                    .order_by(col(FindingRow.id))
                )
            ).all()
        )
        queries = list(
            (
                await db.exec(
                    select(QueryRow)
                    .where(QueryRow.session_id == session_id)
                    .order_by(col(QueryRow.seq))
                )
            ).all()
        )
        query_ids = [q.id for q in queries if q.id is not None]

        # A regrade replaces earlier results.
        await db.exec(delete(OutcomeRow).where(col(OutcomeRow.session_id) == session_id))
        await db.exec(delete(FixResultRow).where(col(FixResultRow.session_id) == session_id))
        if query_ids:
            await db.exec(delete(ClaimAuditRow).where(col(ClaimAuditRow.query_id).in_(query_ids)))

        # 1. Deterministic matching.
        bugs_by_id: dict[str, Bug] = {b.id: b for b in answer.bugs}
        rows_by_id: dict[int, FindingRow] = {f.id: f for f in findings if f.id is not None}
        result = match(
            [BugSpan(b.id, Span(b.file, b.lines[0], b.lines[1])) for b in answer.bugs],
            [
                FindingSpan(fid, Span(f.file, f.line_from, f.line_to))
                for fid, f in rows_by_id.items()
            ],
            self.settings.match_tolerance_lines,
        )
        scopes = [scope_of(q) for q in queries if answered(q)]
        version_tag = self.judge.finding_prompt.version
        results: list[BugResult] = []

        # 2. The judge scores each matched pair.
        for bug_id, finding_id in result.pairs:
            bug, row = bugs_by_id[bug_id], rows_by_id[finding_id]
            code = await self._code(
                session, bug.file, min(bug.lines[0], row.line_from), max(bug.lines[1], row.line_to)
            )
            score = await judge.score_finding(bug, to_finding(row), code)
            if score is None:
                status = OutcomeStatus.UNGRADED
            else:
                status = OutcomeStatus.FOUND if score.mechanism == 2 else OutcomeStatus.PARTIAL
            db.add(
                OutcomeRow(
                    session_id=session_id,
                    bug_id=bug_id,
                    finding_id=finding_id,
                    status=status,
                    assisted=is_assisted(bug, scopes),
                    judge_mechanism=score.mechanism if score else None,
                    judge_fix=score.fix if score else None,
                    judge_notes=score.notes if score else "",
                    prompt_version=version_tag,
                )
            )
            results.append(BugResult(bug, status, score.mechanism if score else None))
        for bug_id in result.missed:
            db.add(
                OutcomeRow(
                    session_id=session_id,
                    bug_id=bug_id,
                    status=OutcomeStatus.MISSED,
                    prompt_version=version_tag,
                )
            )
            results.append(BugResult(bugs_by_id[bug_id], OutcomeStatus.MISSED, None))
        for finding_id in result.extra:
            db.add(
                OutcomeRow(
                    session_id=session_id,
                    finding_id=finding_id,
                    status=OutcomeStatus.EXTRA,
                    prompt_version=version_tag,
                )
            )

        # 3. Design notes.
        notes = session.design_notes.strip()
        if not answer.design_notes:
            session.design_score, session.design_rationale = None, NO_REFERENCE
        elif not notes:
            session.design_score, session.design_rationale = 0, NO_NOTES
        else:
            design = await judge.score_design(list(answer.design_notes), notes)
            session.design_score = design.score if design else None
            session.design_rationale = design.notes if design else NO_SCORE

        # 4. Audit of the assistant's claims.
        for q in queries:
            if not answered(q) or q.id is None or q.reply is None:
                continue
            label = await label_claim(
                judge, list(answer.bugs), await self._shown(session, q), q.question, q.reply
            )
            if label is None:
                continue  # left unaudited rather than labelled by guess
            db.add(
                ClaimAuditRow(
                    query_id=q.id,
                    verdict=label.verdict,
                    relied_on=relied_on(label.verdict, scope_of(q), results),
                    rationale=label.rationale,
                    prompt_version=self.judge.audit_prompt.version,
                )
            )

        # 5. The code fix, if one was submitted: location and syntax are checked here,
        #    the judge scores whether it repairs the bug.
        patches = {
            p.file: p
            for p in (
                await db.exec(select(PatchRow).where(PatchRow.session_id == session_id))
            ).all()
        }
        fixed_on_target: set[str] = set()
        for bug in answer.bugs:
            patch = patches.get(bug.file)
            fix = FixResultRow(
                session_id=session_id,
                bug_id=bug.id,
                submitted=patch is not None,
                prompt_version=self.judge.patch_prompt.version,
            )
            if patch is not None:
                original = await self.store.read_src(pid, version, bug.file)
                fix.on_target = touches_bug(
                    changed_ranges(original, patch.content),
                    bug,
                    self.settings.match_tolerance_lines,
                )
                if bug.file.endswith(".py"):
                    fix.syntax_error = python_syntax_error(patch.content)
                fixed = await judge.score_patch(bug, patch.diff)
                if fixed is not None:
                    fix.judge_fix, fix.judge_notes = fixed.fix, fixed.notes
                if fix.on_target:
                    fixed_on_target.add(bug.id)
            db.add(fix)

        # 6. Tracker, then mark the session graded. A bug whose lines the user fixed was
        #    located, even with no finding flagged, so it does not count as a miss.
        await apply_session(
            db,
            session,
            [
                (
                    r.bug.category,
                    OutcomeStatus.UNGRADED
                    if r.status is OutcomeStatus.MISSED and r.bug.id in fixed_on_target
                    else r.status,
                )
                for r in results
            ],
        )
        session.graded_at = utcnow()
        session.grade_error = None
        db.add(session)
        await db.commit()
