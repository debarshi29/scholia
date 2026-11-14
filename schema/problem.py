"""Problem metadata (``meta.json``). Safe to serve: contains no answer data."""

from enum import StrEnum

from pydantic import Field

from schema._base import NonEmptyStr, ProblemId, StrictModel


class Source(StrEnum):
    SWEBENCH = "swebench"
    BUGSINPY = "bugsinpy"
    PLANTED = "planted"
    """A bug planted in a tested algorithm repo by a deterministic mutation (Tier 2)."""


class ProblemMeta(StrictModel):
    problem_id: ProblemId
    version: int = Field(ge=1)
    tier: int = Field(ge=0, le=3)
    source: Source
    upstream_id: NonEmptyStr
    """Identifier in the source dataset, e.g. a SWE-bench ``instance_id``."""
    origin_repo: NonEmptyStr
    commit: NonEmptyStr
    licence: NonEmptyStr
    """SPDX identifier, checked against the allowlist in ``corpus/filters.py``."""
    line_count: int = Field(ge=1)
    file_count: int = Field(ge=1)
