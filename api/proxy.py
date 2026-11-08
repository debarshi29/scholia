"""Assistant proxy: the only path from a live session to a model (invariant 2).

Constrained mode (local Qwen) checks, in this order (invariant 3):
  1. a selection exists and is valid;
  2. the rendered prompt (system + template + selected lines + question), counted with
     the real Qwen tokenizer, is at most ``ctx_cap``;
  3. ``questions_used < q_budget``.
Only the selected lines are sent: never the rest of the file, other files, the file
path or problem metadata (invariant 4). Refusals cost no budget but are logged, as is
every other exchange (invariant 6).

Realistic mode (Gemini) sends the whole file the selection is in, or every file of the
problem when nothing is selected, has no budget, and is still logged. It only runs for
problems whose licence is on the allowlist (invariant 7).
"""

import time
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.backends.base import BackendError, ChatBackend, ChatMessage
from api.config import Settings
from api.db import QueryRow, SessionRow
from api.problems import ProblemFileError, ProblemStore
from api.tokens import TokenCounter, count_messages
from corpus.filters import is_allowed_licence
from schema import AssistantMode

SYSTEM_CONSTRAINED = (
    "You are a code assistant. The user is reading a Python code base and shows you a "
    "fragment of one file, with line numbers. You can see only this fragment. "
    "Answer the user's question about it concisely."
)
SYSTEM_REALISTIC = (
    "You are a code assistant. The user is reading a Python code base and shares whole "
    "files with you, with line numbers. Answer the user's question concisely."
)


class RefusalReason(StrEnum):
    NO_SELECTION = "no_selection"
    INVALID_SELECTION = "invalid_selection"
    QUESTION_TOO_LONG = "question_too_long"
    OVER_CTX_CAP = "over_ctx_cap"
    BUDGET_EXHAUSTED = "budget_exhausted"
    LICENCE_NOT_ALLOWED = "licence_not_allowed"
    BACKEND_ERROR = "backend_error"


class AskRequest(BaseModel):
    file: str | None = None
    line_from: int | None = Field(default=None, ge=1)
    line_to: int | None = Field(default=None, ge=1)
    question: str = Field(min_length=1)


class AskResult(BaseModel):
    """Refusals are normal results (HTTP 200, ``refused: true``), not errors."""

    query_id: int
    seq: int
    refused: bool
    reason: RefusalReason | None = None
    reply: str | None = None
    model: str
    tokens: int | None = None
    ctx_cap: int | None = None
    """Constrained mode only."""
    questions_used: int
    q_budget: int | None = None
    """Constrained mode only."""


class _Refusal(Exception):
    def __init__(self, reason: RefusalReason, tokens: int | None = None) -> None:
        self.reason = reason
        self.tokens = tokens


def numbered(lines: list[str], first: int) -> str:
    width = len(str(first + len(lines) - 1))
    return "\n".join(f"{n:>{width}} | {line}" for n, line in enumerate(lines, start=first))


def constrained_messages(fragment: list[str], first: int, question: str) -> list[ChatMessage]:
    """The complete Constrained-mode prompt: neutral system prompt, the lines, the question."""
    last = first + len(fragment) - 1
    user = (
        f"Lines {first}-{last}:\n```python\n{numbered(fragment, first)}\n```\n\n"
        f"Question: {question}"
    )
    return [
        ChatMessage(role="system", content=SYSTEM_CONSTRAINED),
        ChatMessage(role="user", content=user),
    ]


def realistic_messages(
    files: dict[str, list[str]], question: str, selection: tuple[str, int, int] | None
) -> list[ChatMessage]:
    parts = [
        f"File `{path}`:\n```python\n{numbered(lines, 1)}\n```" for path, lines in files.items()
    ]
    if selection:
        path, a, b = selection
        parts.append(f"I am looking at lines {a}-{b} of `{path}`.")
    parts.append(f"Question: {question}")
    return [
        ChatMessage(role="system", content=SYSTEM_REALISTIC),
        ChatMessage(role="user", content="\n\n".join(parts)),
    ]


async def questions_used(db: AsyncSession, session_id: str) -> int:
    """Answered questions only: refusals and backend failures cost no budget."""
    stmt = select(func.count()).where(
        QueryRow.session_id == session_id, col(QueryRow.refused_reason).is_(None)
    )
    return int((await db.exec(stmt)).one())


async def _next_seq(db: AsyncSession, session_id: str) -> int:
    stmt = select(func.max(QueryRow.seq)).where(QueryRow.session_id == session_id)
    return int((await db.exec(stmt)).one() or 0) + 1


class Proxy:
    def __init__(
        self,
        settings: Settings,
        counter: TokenCounter,
        local: ChatBackend,
        realistic: ChatBackend | None,
        store: ProblemStore,
    ) -> None:
        self.settings = settings
        self.counter = counter
        self.local = local
        self.realistic = realistic
        self.store = store
        # Fixed prompt overhead (system prompt + template), computed once; shown in the UI.
        self.constrained_overhead = count_messages(counter, constrained_messages([], 1, ""))

    async def ask(self, db: AsyncSession, session: SessionRow, req: AskRequest) -> AskResult:
        constrained = session.mode == AssistantMode.CONSTRAINED
        backend = self.local if constrained else self.realistic
        model = backend.model if backend else "(realistic backend not configured)"
        row = QueryRow(
            session_id=session.id,
            seq=await _next_seq(db, session.id),
            file=req.file,
            line_from=req.line_from,
            line_to=req.line_to,
            question=req.question,
            model=model,
        )
        try:
            if constrained:
                messages = await self._constrained(db, session, req, row)
            else:
                messages = await self._realistic(session, req, row)
            if backend is None:
                raise _Refusal(RefusalReason.BACKEND_ERROR, row.tokens)
            started = time.perf_counter()
            try:
                row.reply = await backend.chat(messages, self.settings.max_reply_tokens)
            except BackendError as exc:
                row.reply = str(exc)  # logged for diagnosis; never returned as an answer
                raise _Refusal(RefusalReason.BACKEND_ERROR, row.tokens) from exc
            finally:
                row.latency_ms = round((time.perf_counter() - started) * 1000)
        except _Refusal as refusal:
            row.refused_reason = refusal.reason.value
            row.tokens = refusal.tokens

        db.add(row)
        await db.commit()
        await db.refresh(row)
        assert row.id is not None
        reason = RefusalReason(row.refused_reason) if row.refused_reason else None
        return AskResult(
            query_id=row.id,
            seq=row.seq,
            refused=reason is not None,
            reason=reason,
            reply=None if reason else row.reply,
            model=model,
            tokens=row.tokens,
            ctx_cap=session.ctx_cap if constrained else None,
            questions_used=await questions_used(db, session.id),
            q_budget=session.q_budget if constrained else None,
        )

    async def _selected_file(self, session: SessionRow, req: AskRequest) -> list[str]:
        assert req.file is not None
        try:
            lines = await self.store.read_src_lines(
                session.problem_id, session.problem_version, req.file
            )
        except ProblemFileError as exc:
            raise _Refusal(RefusalReason.INVALID_SELECTION) from exc
        if req.line_from is not None or req.line_to is not None:
            a, b = req.line_from, req.line_to
            if a is None or b is None or not 1 <= a <= b <= len(lines):
                raise _Refusal(RefusalReason.INVALID_SELECTION)
        return lines

    def _check_question(self, req: AskRequest) -> None:
        if len(req.question) > self.settings.max_question_chars:
            raise _Refusal(RefusalReason.QUESTION_TOO_LONG)

    async def _constrained(
        self, db: AsyncSession, session: SessionRow, req: AskRequest, row: QueryRow
    ) -> list[ChatMessage]:
        # 1. A selection exists (and points at real lines of a served file).
        if req.file is None or req.line_from is None or req.line_to is None:
            raise _Refusal(RefusalReason.NO_SELECTION)
        lines = await self._selected_file(session, req)
        # 2. Size: question length, then the exact token count against ctx_cap.
        self._check_question(req)
        fragment = lines[req.line_from - 1 : req.line_to]
        messages = constrained_messages(fragment, req.line_from, req.question)
        tokens = count_messages(self.counter, messages)
        row.tokens = tokens
        if tokens > session.ctx_cap:
            raise _Refusal(RefusalReason.OVER_CTX_CAP, tokens)
        # 3. Budget.
        if await questions_used(db, session.id) >= session.q_budget:
            raise _Refusal(RefusalReason.BUDGET_EXHAUSTED, tokens)
        return messages

    async def _realistic(
        self, session: SessionRow, req: AskRequest, row: QueryRow
    ) -> list[ChatMessage]:
        meta = await self.store.meta(session.problem_id, session.problem_version)
        if not is_allowed_licence(meta.licence):
            raise _Refusal(RefusalReason.LICENCE_NOT_ALLOWED)
        selection: tuple[str, int, int] | None = None
        if req.file is not None:
            files = {req.file: await self._selected_file(session, req)}
            if req.line_from is not None and req.line_to is not None:
                selection = (req.file, req.line_from, req.line_to)
        else:
            paths = await self.store.src_files(session.problem_id, session.problem_version)
            files = {
                p: await self.store.read_src_lines(session.problem_id, session.problem_version, p)
                for p in paths
            }
        self._check_question(req)
        messages = realistic_messages(files, req.question, selection)
        row.tokens = count_messages(self.counter, messages)  # approximate for Gemini
        return messages
