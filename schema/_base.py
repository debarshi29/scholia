"""Shared base model and validated primitive types."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ProblemId = Annotated[str, StringConstraints(pattern=r"^P-\d{4,}$")]
"""Problem identifier, e.g. ``P-0001``."""

RelPath = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^(?![/\])(?!.*(?:^|[/\])\.\.(?:[/\]|$)).+$"),
]
"""A relative POSIX-style path inside a problem's ``src/`` (no leading slash, no ``..``)."""

LineNo = Annotated[int, Field(ge=1)]
"""1-indexed line number."""

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class StrictModel(BaseModel):
    """Immutable model that rejects unknown fields: every boundary is explicit."""

    model_config = ConfigDict(frozen=True, extra="forbid")
