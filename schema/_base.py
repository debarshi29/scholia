"""Shared base model and validated primitive types."""

from pathlib import PurePosixPath
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


def _check_rel_path(value: str) -> str:
    normalised = value.replace("\\", "/")
    path = PurePosixPath(normalised)
    if path.is_absolute() or ".." in path.parts or normalised.startswith("/"):
        raise ValueError(f"path must be relative to the problem's src/: {value!r}")
    return normalised


ProblemId = Annotated[str, StringConstraints(pattern=r"^P-\d{4,}$")]
"""Problem identifier, e.g. ``P-0001``."""

RelPath = Annotated[str, StringConstraints(min_length=1), AfterValidator(_check_rel_path)]
"""A relative POSIX-style path inside a problem's ``src/`` (no leading slash, no ``..``)."""

LineNo = Annotated[int, Field(ge=1)]
"""1-indexed line number."""

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class StrictModel(BaseModel):
    """Immutable model that rejects unknown fields: every boundary is explicit."""

    model_config = ConfigDict(frozen=True, extra="forbid")
