"""Answer key for a problem (``answer.json``). Never served before submit."""

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from schema._base import LineNo, NonEmptyStr, ProblemId, RelPath, StrictModel
from schema.taxonomy import BugCategory


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CategorySource(StrEnum):
    """Who assigned the category: a reviewer, or the corpus-build LLM pass."""

    MANUAL = "manual"
    LLM = "llm"


DesignNote = NonEmptyStr
"""A single expected design observation, stored as a plain string in ``answer.json``."""


class Bug(StrictModel):
    id: NonEmptyStr
    file: RelPath
    lines: tuple[LineNo, LineNo]
    category: BugCategory
    category_source: CategorySource = CategorySource.MANUAL
    severity: Severity = Severity.MEDIUM
    mechanism: NonEmptyStr
    fix_diff: str
    killing_test: str | None = None

    @model_validator(mode="after")
    def _ordered_lines(self) -> Self:
        if self.lines[0] > self.lines[1]:
            raise ValueError(f"bug {self.id}: lines must be [start, end] with start <= end")
        return self


class AnswerKey(StrictModel):
    problem_id: ProblemId
    version: int = Field(ge=1)
    bugs: list[Bug] = Field(min_length=1)
    design_notes: list[DesignNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_bug_ids(self) -> Self:
        ids = [b.id for b in self.bugs]
        if len(ids) != len(set(ids)):
            raise ValueError("bug ids must be unique within an answer key")
        return self
