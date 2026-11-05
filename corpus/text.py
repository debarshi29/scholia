"""Line handling that agrees with git and the editor: lines end at ``\n`` only.

``str.splitlines`` also breaks on form feeds, ``\x1c``-``\x1e``, ``\u2028`` and more,
which would shift line numbers relative to the patch and the viewer.
"""

import re

_KEEP_NL = re.compile(r"(?<=\n)")


def split_lines(text: str) -> list[str]:
    """Lines without terminators (a trailing ``\r`` is dropped too)."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [ln[:-1] if ln.endswith("\r") else ln for ln in lines]


def split_lines_keepends(text: str) -> list[str]:
    """Lines with their ``\n`` / ``\r\n`` terminators, so joining restores ``text``."""
    return [part for part in _KEEP_NL.split(text) if part]


def line_count(text: str) -> int:
    return len(split_lines(text))
