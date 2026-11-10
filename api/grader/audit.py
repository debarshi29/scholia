"""Assistant-claim audit.

The judge labels each answered assistant reply ``correct``, ``wrong`` or
``unverifiable`` against the answer key. Whether the user *relied on* a wrong claim,
and whether a bug was found with assistance, are computed here deterministically from
line ranges and outcomes.
"""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from api.grader.judge import Judge
from api.grader.match import Span, overlap, same_file
from schema import Bug, ClaimVerdict, OutcomeStatus


class ClaimLabel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verdict: ClaimVerdict
    rationale: str = Field(default="", max_length=1000)


@dataclass(frozen=True)
class QueryScope:
    """What a query was about. No file means the whole problem (Realistic mode);
    a file without lines means that whole file."""

    file: str | None
    line_from: int | None
    line_to: int | None

    def covers(self, bug: Bug) -> bool:
        if self.file is None:
            return True
        if self.line_from is None or self.line_to is None:
            return same_file(self.file, bug.file)
        bug_span = Span(bug.file, bug.lines[0], bug.lines[1])
        return overlap(bug_span, Span(self.file, self.line_from, self.line_to)) > 0


@dataclass(frozen=True)
class BugResult:
    bug: Bug
    status: OutcomeStatus
    mechanism: int | None
    """Judge mechanism score for a matched bug; ``None`` when missed or ungraded."""


def is_assisted(bug: Bug, answered: list[QueryScope]) -> bool:
    """A matched bug is assisted when any answered query covered its lines. v1 has no
    per-finding timestamps, so the order of asking and flagging is not considered."""
    return any(scope.covers(bug) for scope in answered)


def relied_on(verdict: ClaimVerdict, scope: QueryScope, results: list[BugResult]) -> bool:
    """True when a wrong claim covered a key bug that the user then missed, or explained
    less than fully correctly (mechanism score below 2)."""
    if verdict is not ClaimVerdict.WRONG:
        return False
    for r in results:
        if not scope.covers(r.bug):
            continue
        if r.status is OutcomeStatus.MISSED:
            return True
        if r.mechanism is not None and r.mechanism < 2:
            return True
    return False


def render_claim(bugs: list[Bug], shown: str, question: str, reply: str) -> str:
    key = "\n".join(
        f"- {b.file} lines {b.lines[0]}-{b.lines[1]} ({b.category.value}): {b.mechanism}"
        for b in bugs
    )
    return (
        f"## ANSWER KEY\n{key}\n\n"
        f"## CODE THE ASSISTANT WAS SHOWN\n```python\n{shown}\n```\n\n"
        f"## QUESTION\n{question}\n\n"
        f"## REPLY\n{reply}\n"
    )


async def label_claim(
    judge: Judge, bugs: list[Bug], shown: str, question: str, reply: str
) -> ClaimLabel | None:
    """``None`` when the judge gave no valid label: the reply is then left unaudited."""
    return await judge.ask(
        judge.audit_prompt, render_claim(bugs, shown, question, reply), ClaimLabel
    )
