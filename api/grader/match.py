"""Deterministic matching of findings to key bugs (invariant 9). Pure functions, no I/O.

A finding matches a bug when the files are equal and the finding's line range overlaps
the bug's range widened by ``tolerance`` lines on each side. Assignment is one-to-one
and greedy by overlap size. Ties go to the earlier bug, then the earlier finding, so
the same report always grades the same way. The LLM never takes part in this step.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """An inclusive, 1-indexed line range in one file."""

    file: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 1 or self.end < self.start:
            raise ValueError(f"invalid span {self.start}-{self.end}")


@dataclass(frozen=True)
class BugSpan:
    id: str
    span: Span


@dataclass(frozen=True)
class FindingSpan:
    id: int
    span: Span


@dataclass(frozen=True)
class MatchResult:
    pairs: tuple[tuple[str, int], ...]
    """``(bug id, finding id)``, in bug order."""
    missed: tuple[str, ...]
    """Bug ids with no finding, in bug order."""
    extra: tuple[int, ...]
    """Finding ids with no bug, in finding order."""


def same_file(a: str, b: str) -> bool:
    return a.replace("\\", "/") == b.replace("\\", "/")


def overlap(a: Span, b: Span, widen_a: int = 0) -> int:
    """Number of lines ``b`` shares with ``a`` after widening ``a`` by ``widen_a`` each side."""
    if not same_file(a.file, b.file):
        return 0
    lo = max(max(1, a.start - widen_a), b.start)
    hi = min(a.end + widen_a, b.end)
    return max(0, hi - lo + 1)


def match(bugs: Sequence[BugSpan], findings: Sequence[FindingSpan], tolerance: int) -> MatchResult:
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    candidates = [
        (-size, bi, fi)
        for bi, bug in enumerate(bugs)
        for fi, finding in enumerate(findings)
        if (size := overlap(bug.span, finding.span, tolerance)) > 0
    ]
    bug_to_finding: dict[int, int] = {}
    taken: set[int] = set()
    for _size, bi, fi in sorted(candidates):
        if bi not in bug_to_finding and fi not in taken:
            bug_to_finding[bi] = fi
            taken.add(fi)
    return MatchResult(
        pairs=tuple((bugs[bi].id, findings[fi].id) for bi, fi in sorted(bug_to_finding.items())),
        missed=tuple(b.id for bi, b in enumerate(bugs) if bi not in bug_to_finding),
        extra=tuple(f.id for fi, f in enumerate(findings) if fi not in taken),
    )
