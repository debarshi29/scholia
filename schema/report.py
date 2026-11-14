"""User-submitted report: findings, free-text design notes and optional code fixes."""

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


class FilePatch(StrictModel):
    """The user's edited copy of one served file: their attempt at fixing the bug."""

    file: RelPath
    content: str = Field(max_length=400_000)


class Report(StrictModel):
    findings: list[Finding] = Field(default_factory=list)
    design_notes: str = ""
    patches: list[FilePatch] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_patch_per_file(self) -> Self:
        files = [p.file for p in self.patches]
        if len(files) != len(set(files)):
            raise ValueError("at most one patch per file")
        return self
