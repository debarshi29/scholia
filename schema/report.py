"""User-submitted report: findings plus free-text design notes."""

from typing import Self

from pydantic import Field, model_validator

from schema._base import LineNo, RelPath, StrictModel
from schema.taxonomy import BugCategory


class Finding(StrictModel):
    file: RelPath
    line_from: LineNo
    line_to: LineNo
    category: BugCategory
    explanation: str = Field(min_length=1)
    fix: str = ""

    @model_validator(mode="after")
    def _ordered_lines(self) -> Self:
        if self.line_from > self.line_to:
            raise ValueError("line_from must be <= line_to")
        return self


class Report(StrictModel):
    findings: list[Finding] = Field(default_factory=list)
    design_notes: str = ""
