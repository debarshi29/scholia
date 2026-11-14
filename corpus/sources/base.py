"""What a Tier 0 source yields: one upstream bug with its gold patch and verifying tests."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

from schema import Source


@dataclass(frozen=True)
class Candidate:
    source: Source
    upstream_id: str
    repo: str
    """GitHub ``owner/name``."""
    commit: str
    """Buggy commit the patch applies to."""
    patch: str
    """Gold fix patch (may touch tests; the build excludes them)."""
    issue: str
    test_patch: str = ""
    failing_tests: list[str] = field(default_factory=list)
    """Tests that fail before the fix and pass after it."""
    buggy_files: dict[str, str] = field(default_factory=dict)
    """Buggy text of files that is not in the repo at ``commit`` (planted bugs); the
    ``patch`` fixes these. Files not listed are read from the repo."""
    min_lines: int | None = None
    """Per-source override of the minimum file length (algorithm files are short)."""


class CandidateSource(Protocol):
    source: Source

    def candidates(self) -> Iterator[Candidate]: ...
