"""Strip hints from buggy source without changing semantics or line numbers.

Removed:
- comments containing issue/ticket references anywhere in the file;
- TODO/FIXME/XXX/HACK comments near a bug;
- comments near a bug that point at the defect ("bug", "fix", "wrong", ...).

A full-line comment becomes an empty line; an inline comment is cut off the code.
Docstrings and other strings are never touched: they are part of the program.
The result is checked: same line count and an identical AST, or ``SanitiseError``.
"""

import ast
import io
import re
import tokenize
import warnings
from dataclasses import dataclass, field
from enum import StrEnum

HINT_WINDOW = 3
"""Lines around a bug range in which hint comments are removed."""

_ISSUE = re.compile(
    r"(?:#\d{2,}\b|\b(?:gh|bpo|issue|ticket|pr|bug)[\s-]?#?\d{2,}\b"
    r"|github\.com/\S+/(?:issues|pull)/\d+|code\.djangoproject\.com/ticket/\d+)",
    re.IGNORECASE,
)
_MARKER = re.compile(r"\b(?:TODO|FIXME|XXX|HACK)\b")
_FIX_HINT = re.compile(
    r"\b(?:bug(?:gy|s)?|fix(?:e[ds])?|broken|wrong|incorrect(?:ly)?|workaround|regression"
    r"|should(?:n't| not)? (?:be|have|use|handle|check)|doesn't work|does not work)\b",
    re.IGNORECASE,
)


class RemovalReason(StrEnum):
    ISSUE_REF = "issue_ref"
    MARKER = "marker"
    FIX_HINT = "fix_hint"


@dataclass(frozen=True)
class Removal:
    line: int
    reason: RemovalReason
    text: str


@dataclass(frozen=True)
class SanitiseResult:
    text: str
    removals: list[Removal] = field(default_factory=list)


class SanitiseError(ValueError):
    pass


def _near_bug(line: int, bug_ranges: list[tuple[int, int]]) -> bool:
    return any(a - HINT_WINDOW <= line <= b + HINT_WINDOW for a, b in bug_ranges)


def _reason(comment: str, line: int, bug_ranges: list[tuple[int, int]]) -> RemovalReason | None:
    if _ISSUE.search(comment):
        return RemovalReason.ISSUE_REF
    if _near_bug(line, bug_ranges):
        if _MARKER.search(comment):
            return RemovalReason.MARKER
        if _FIX_HINT.search(comment):
            return RemovalReason.FIX_HINT
    return None


def _parse(source: str) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(source)


def sanitise(source: str, bug_ranges: list[tuple[int, int]]) -> SanitiseResult:
    """Return ``source`` with hint comments removed. ``bug_ranges`` are 1-indexed, inclusive."""
    try:
        before = ast.dump(_parse(source))
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (SyntaxError, tokenize.TokenError) as exc:
        raise SanitiseError(f"cannot tokenize source: {exc}") from exc

    lines = source.splitlines(keepends=True)
    removals: list[Removal] = []
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        row, col = tok.start
        reason = _reason(tok.string, row, bug_ranges)
        if reason is None:
            continue
        original = lines[row - 1]
        body = original.rstrip("\r\n")
        ending = original[len(body) :]
        code = body[:col].rstrip()
        lines[row - 1] = code + ending
        removals.append(Removal(line=row, reason=reason, text=tok.string))

    out = "".join(lines)
    if len(out.splitlines()) != len(source.splitlines()):
        raise SanitiseError("line count changed")
    if ast.dump(_parse(out)) != before:
        raise SanitiseError("AST changed")
    return SanitiseResult(text=out, removals=removals)
