"""Unified-diff parsing and mapping of changes onto buggy-version line numbers.

Hunk headers in dataset patches are not always exact for the commit they claim
(``git apply`` tolerates offsets), so line numbers are found by locating each
hunk's old-side content in the real buggy file, nearest the stated position.
"""

import re
from dataclasses import dataclass, field

from corpus.text import split_lines

CLUSTER_GAP = 10
"""Changed lines further apart than this become separate bug regions."""

_DIFF_GIT = re.compile(r"^diff --git a/(?P<a>\S+) b/(?P<b>\S+)$")
_HUNK = re.compile(r"^@@ -(?P<os>\d+)(?:,(?P<oc>\d+))? \+(?P<ns>\d+)(?:,(?P<nc>\d+))? @@")


class PatchError(ValueError):
    pass


@dataclass
class Hunk:
    old_start: int
    """1-indexed start of the old side as stated in the header."""
    old_lines: list[str] = field(default_factory=list)
    """Old-side content: context plus removed lines, in order."""
    removed: list[int] = field(default_factory=list)
    """Indexes into ``old_lines`` that the patch deletes or replaces."""
    insert_after: list[int] = field(default_factory=list)
    """Indexes into ``old_lines`` after which pure insertions happen (-1 = before the first)."""


@dataclass
class FilePatch:
    path: str
    """Path in the buggy (old) version."""
    diff: str
    """This file's section of the patch, starting at ``diff --git``."""
    is_new: bool = False
    is_deleted: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    def locate(self, source: str) -> list[int]:
        """Map every changed point to a 1-indexed line of ``source`` (the buggy file).

        A pure insertion is anchored to the line before it (or line 1 at the top),
        since that is where a reader would have to notice something is missing.
        """
        src = split_lines(source)
        points: list[int] = []
        for h in self.hunks:
            base = _find(src, h)
            points.extend(base + i + 1 for i in h.removed)
            points.extend(max(base + i + 1, 1) for i in h.insert_after)
        return sorted(set(points))

    def changed_regions(self, source: str, gap: int = CLUSTER_GAP) -> list[tuple[int, int]]:
        """Cluster changed lines into inclusive ``(start, end)`` ranges."""
        return cluster(self.locate(source), gap)


def cluster(points: list[int], gap: int = CLUSTER_GAP) -> list[tuple[int, int]]:
    if not points:
        return []
    regions: list[tuple[int, int]] = []
    start = prev = points[0]
    for p in points[1:]:
        if p - prev > gap:
            regions.append((start, prev))
            start = p
        prev = p
    regions.append((start, prev))
    return regions


def _find(src: list[str], h: Hunk) -> int:
    """0-indexed position of the hunk's old side in ``src``, nearest the header's claim."""
    n = len(h.old_lines)
    stated = max(h.old_start - 1, 0)
    if n == 0:
        if stated > len(src):
            raise PatchError("insertion point beyond end of file")
        return stated
    for delta in range(len(src) + 1):
        for pos in (stated - delta, stated + delta) if delta else (stated,):
            if 0 <= pos <= len(src) - n and src[pos : pos + n] == h.old_lines:
                return pos
    raise PatchError(f"hunk at -{h.old_start} does not match the buggy source")


def _split_files(patch: str) -> list[tuple[str, str, list[str]]]:
    sections: list[tuple[str, str, list[str]]] = []
    for line in patch.split("\n"):
        m = _DIFF_GIT.match(line)
        if m:
            sections.append((m["a"], m["b"], [line]))
        elif sections:
            sections[-1][2].append(line)
        elif line.strip():
            raise PatchError("content before first 'diff --git' header")
    if not sections:
        raise PatchError("no 'diff --git' sections found")
    return sections


def _parse_hunks(fp: FilePatch, lines: list[str]) -> None:
    i = 0
    while i < len(lines):
        m = _HUNK.match(lines[i])
        if not m:
            i += 1
            continue
        old_left = int(m["oc"]) if m["oc"] is not None else 1
        new_left = int(m["nc"]) if m["nc"] is not None else 1
        # With an empty old side, git states the line *before* the insertion.
        h = Hunk(old_start=int(m["os"]) + (1 if old_left == 0 else 0))
        last_was_removal = False
        i += 1
        while i < len(lines) and (old_left > 0 or new_left > 0):
            body = lines[i]
            tag = body[:1]
            if tag == " " or body == "":
                h.old_lines.append(body[1:])
                old_left -= 1
                new_left -= 1
                last_was_removal = False
            elif tag == "-":
                h.removed.append(len(h.old_lines))
                h.old_lines.append(body[1:])
                old_left -= 1
                last_was_removal = True
            elif tag == "+":
                if not last_was_removal:
                    h.insert_after.append(len(h.old_lines) - 1)
                new_left -= 1
            elif tag != "\\":  # "\ No newline at end of file" is ignored
                raise PatchError(f"{fp.path}: unexpected hunk line {body!r}")
            i += 1
        if old_left != 0 or new_left != 0:
            raise PatchError(f"{fp.path}: truncated hunk")
        h.insert_after = sorted(set(h.insert_after))
        fp.hunks.append(h)
    if not fp.hunks and not (fp.is_new or fp.is_deleted):
        raise PatchError(f"{fp.path}: no hunks")


def parse_patch(patch: str) -> list[FilePatch]:
    out: list[FilePatch] = []
    for a, b, lines in _split_files(patch):
        first_hunk = next((k for k, ln in enumerate(lines) if ln.startswith("@@")), len(lines))
        header = lines[:first_hunk]
        is_new = any(h.startswith("new file mode") or h == "--- /dev/null" for h in header)
        is_deleted = any(h.startswith("deleted file mode") or h == "+++ /dev/null" for h in header)
        if a != b and not (is_new or is_deleted):
            raise PatchError(f"renames are not supported: {a} -> {b}")
        while lines and lines[-1] == "":
            lines.pop()
        fp = FilePatch(path=a, diff="\n".join(lines) + "\n", is_new=is_new, is_deleted=is_deleted)
        _parse_hunks(fp, lines)
        out.append(fp)
    return out
