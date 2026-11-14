"""Gemini judge: scores matched findings and design notes against the answer key.

The judge only scores (invariant 9): which finding belongs to which bug is decided in
``match.py`` before this module runs. Output must be one JSON object of the expected
shape. On invalid output the call is retried once; after that the result is ``None``
and the caller records ``ungraded``. A score is never guessed.
"""

import logging
import re
from dataclasses import dataclass
from importlib import resources

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.backends.base import BackendError, ChatBackend, ChatMessage
from api.jsonout import parse_model_json
from schema import Bug, Finding

log = logging.getLogger(__name__)

_VERSION = re.compile(r"<!-- version: (\S+) -->\n")


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str


def load_prompt(name: str) -> Prompt:
    raw = resources.files("api.grader").joinpath(f"prompts/{name}.md").read_text("utf-8")
    m = _VERSION.match(raw)
    if not m:
        raise ValueError(f"prompt {name} has no version header")
    return Prompt(version=m[1], text=raw[m.end() :])


class _Scored(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class FindingScore(_Scored):
    mechanism: int = Field(ge=0, le=2)
    fix: int = Field(ge=0, le=2)
    notes: str = Field(default="", max_length=1000)


class PatchScore(_Scored):
    fix: int = Field(ge=0, le=2)
    notes: str = Field(default="", max_length=1000)


class DesignScore(_Scored):
    score: int = Field(ge=0, le=3)
    notes: str = Field(default="", max_length=1000)


NO_SEPARATE_FIX = "(not given separately; any fix is part of the explanation above)"


def render_finding(bug: Bug, finding: Finding, code: str) -> str:
    return (
        "## ANSWER KEY\n"
        f"File: {bug.file}, lines {bug.lines[0]}-{bug.lines[1]}\n"
        f"Category: {bug.category.value}\n"
        f"Mechanism: {bug.mechanism}\n"
        f"Reference fix:\n```diff\n{bug.fix_diff}\n```\n\n"
        "## CODE (buggy version, with line numbers)\n"
        f"```python\n{code}\n```\n\n"
        "## CANDIDATE\n"
        f"Lines flagged: {finding.line_from}-{finding.line_to}\n"
        f"Category chosen: {finding.category.value}\n"
        f"Explanation: {finding.explanation}\n"
        f"Proposed fix: {finding.fix or NO_SEPARATE_FIX}\n"
    )


def render_patch(bug: Bug, user_diff: str) -> str:
    return (
        "## ANSWER KEY\n"
        f"File: {bug.file}, lines {bug.lines[0]}-{bug.lines[1]}\n"
        f"Mechanism: {bug.mechanism}\n"
        f"Reference fix:\n```diff\n{bug.fix_diff}\n```\n\n"
        "## CANDIDATE\n"
        f"Their change to the same buggy file:\n```diff\n{user_diff}\n```\n"
    )


def render_design(reference: list[str], notes: str) -> str:
    points = "\n".join(f"- {r}" for r in reference)
    return f"## REFERENCE NOTES\n{points}\n\n## CANDIDATE\n{notes}\n"


class Judge:
    """Wraps a chat backend. With no backend, every call returns ``None`` (ungraded)."""

    def __init__(self, backend: ChatBackend | None, max_tokens: int) -> None:
        self.backend = backend
        self.max_tokens = max_tokens
        self.finding_prompt = load_prompt("judge_finding")
        self.design_prompt = load_prompt("judge_design")
        self.audit_prompt = load_prompt("audit")
        self.patch_prompt = load_prompt("judge_patch")

    @property
    def model(self) -> str | None:
        return self.backend.model if self.backend else None

    async def ask[T: BaseModel](self, prompt: Prompt, user: str, shape: type[T]) -> T | None:
        if self.backend is None:
            return None
        messages = [
            ChatMessage(role="system", content=prompt.text),
            ChatMessage(role="user", content=user),
        ]
        for attempt in (1, 2):  # one retry on invalid output, then ungraded
            try:
                raw = await self.backend.chat(messages, self.max_tokens)
            except BackendError as exc:
                log.warning(
                    "judge backend failed", extra={"prompt": prompt.version, "err": str(exc)}
                )
                return None
            try:
                return parse_model_json(raw, shape)
            except ValidationError:
                log.warning(
                    "judge output invalid",
                    extra={"prompt": prompt.version, "attempt": attempt, "raw": raw[:300]},
                )
        return None

    async def score_finding(self, bug: Bug, finding: Finding, code: str) -> FindingScore | None:
        return await self.ask(self.finding_prompt, render_finding(bug, finding, code), FindingScore)

    async def score_patch(self, bug: Bug, user_diff: str) -> PatchScore | None:
        return await self.ask(self.patch_prompt, render_patch(bug, user_diff), PatchScore)

    async def score_design(self, reference: list[str], notes: str) -> DesignScore | None:
        return await self.ask(self.design_prompt, render_design(reference, notes), DesignScore)
