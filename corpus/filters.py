"""Candidate filters: file counts, line counts, test-file exclusion and the licence allowlist."""

import re
from enum import StrEnum
from pathlib import PurePosixPath

MIN_LINES = 150
MAX_LINES = 500
MAX_FILES = 2

LICENCE_ALLOWLIST: frozenset[str] = frozenset(
    {"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "PSF-2.0"}
)
"""SPDX ids considered permissive. Only these problems may be sent to Gemini (invariant 7)."""


class DropReason(StrEnum):
    NO_SOURCE_FILES = "no_source_files"
    TOO_MANY_FILES = "too_many_files"
    NON_PYTHON = "non_python"
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    LICENCE_NOT_ALLOWED = "licence_not_allowed"
    LICENCE_UNKNOWN = "licence_unknown"
    PATCH_UNPARSEABLE = "patch_unparseable"
    PATCH_ADDS_FILE = "patch_adds_file"
    SOURCE_UNPARSEABLE = "source_unparseable"
    CHECKOUT_FAILED = "checkout_failed"
    CLASSIFY_FAILED = "classify_failed"
    ALREADY_PUBLISHED = "already_published"


_TEST_DIRS = {"test", "tests", "testing"}


def is_test_path(path: str) -> bool:
    p = PurePosixPath(path)
    if any(part in _TEST_DIRS for part in p.parts[:-1]):
        return True
    name = p.name
    return name == "conftest.py" or name.startswith("test_") or name.endswith("_test.py")


def source_files(paths: list[str]) -> list[str]:
    """Paths a gold patch touches, minus tests. Order is preserved."""
    return [p for p in paths if not is_test_path(p)]


def check_file_set(paths: list[str]) -> DropReason | None:
    if not paths:
        return DropReason.NO_SOURCE_FILES
    if len(paths) > MAX_FILES:
        return DropReason.TOO_MANY_FILES
    if any(not p.endswith(".py") for p in paths):
        return DropReason.NON_PYTHON
    return None


def line_count(text: str) -> int:
    return len(text.splitlines())


def check_line_counts(texts: list[str]) -> DropReason | None:
    """Every file must be within [MIN_LINES, MAX_LINES]. v1 does no cropping."""
    counts = [line_count(t) for t in texts]
    if any(c > MAX_LINES for c in counts):
        return DropReason.TOO_LONG
    if any(c < MIN_LINES for c in counts):
        return DropReason.TOO_SHORT
    return None


def is_allowed_licence(spdx: str | None) -> bool:
    return spdx is not None and spdx in LICENCE_ALLOWLIST


_WS = re.compile(r"\s+")


def detect_licence_from_text(text: str) -> str | None:
    """Recognise common permissive licences from a LICENSE file's text.

    Used only when GitHub reports ``NOASSERTION`` (e.g. sympy, sphinx), so it is
    deliberately conservative: anything unrecognised returns ``None`` and is dropped.
    """
    t = _WS.sub(" ", text).lower()
    if "apache license" in t and "version 2.0" in t:
        return "Apache-2.0"
    if "permission is hereby granted, free of charge" in t:
        return "MIT"
    if "redistribution and use in source and binary forms" in t:
        if "neither the name" in t or "names of its contributors may" in t:
            return "BSD-3-Clause"
        return "BSD-2-Clause"
    return None
