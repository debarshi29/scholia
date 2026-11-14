"""Deterministic checks on a submitted code fix. Pure functions, no I/O.

A fix is the user's edited copy of a served file. Here it is compared with the buggy
original: which original lines changed, whether those lines are the key bug's lines,
and whether the result still parses. Whether the fix is *right* is scored by the judge
(and by tests, where a problem has runnable ones); that is not decided here.
"""

import ast
import difflib
import warnings

from api.grader.match import Span, overlap
from corpus.text import split_lines
from schema import Bug


def unified(path: str, original: str, patched: str, context: int = 3) -> str:
    """A git-style unified diff from the buggy original to the user's version."""
    lines = difflib.unified_diff(
        split_lines(original),
        split_lines(patched),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=context,
        lineterm="",
    )
    body = "\n".join(lines)
    return f"diff --git a/{path} b/{path}\n{body}\n" if body else ""


def changed_ranges(original: str, patched: str) -> list[tuple[int, int]]:
    """Inclusive 1-indexed ranges of *original* lines that the fix replaces or deletes.
    A pure insertion is anchored to the line before it (line 1 at the top of the file),
    the same convention the answer key uses for fixes that only add lines."""
    matcher = difflib.SequenceMatcher(
        a=split_lines(original), b=split_lines(patched), autojunk=False
    )
    ranges: list[tuple[int, int]] = []
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            ranges.append((i1 + 1, i2))
        elif tag == "insert":
            anchor = max(i1, 1)
            ranges.append((anchor, anchor))
    return ranges


def touches_bug(ranges: list[tuple[int, int]], bug: Bug, tolerance: int) -> bool:
    """True when any changed range overlaps the bug's lines widened by ``tolerance``."""
    key = Span(bug.file, bug.lines[0], bug.lines[1])
    return any(overlap(key, Span(bug.file, a, b), tolerance) > 0 for a, b in ranges)


def python_syntax_error(source: str) -> str | None:
    """``None`` when ``source`` parses as Python, otherwise a one-line description."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            ast.parse(source)
    except SyntaxError as exc:
        return f"line {exc.lineno}: {exc.msg}"
    return None
