import pytest

from corpus.filters import (
    DropReason,
    check_file_set,
    check_line_counts,
    detect_licence_from_text,
    is_allowed_licence,
    is_test_path,
    source_files,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("django/db/models/query.py", False),
        ("tests/test_x.py", True),
        ("astropy/modeling/tests/helpers.py", True),
        ("pkg/test_utils.py", True),
        ("pkg/utils_test.py", True),
        ("conftest.py", True),
        ("pkg/testament.py", False),
        ("sklearn/utils/_testing.py", False),
    ],
)
def test_is_test_path(path: str, expected: bool) -> None:
    assert is_test_path(path) is expected


def test_source_files_drops_tests() -> None:
    assert source_files(["a.py", "tests/test_a.py", "b.py"]) == ["a.py", "b.py"]


@pytest.mark.parametrize(
    ("paths", "reason"),
    [
        ([], DropReason.NO_SOURCE_FILES),
        (["a.py", "b.py", "c.py"], DropReason.TOO_MANY_FILES),
        (["a.py", "setup.cfg"], DropReason.NON_PYTHON),
        (["a.py"], None),
        (["a.py", "b.py"], None),
    ],
)
def test_check_file_set(paths: list[str], reason: DropReason | None) -> None:
    assert check_file_set(paths) == reason


def _text(n: int) -> str:
    return "x = 1\n" * n


@pytest.mark.parametrize(
    ("sizes", "reason"),
    [
        ([150], None),
        ([500], None),
        ([149], DropReason.TOO_SHORT),
        ([501], DropReason.TOO_LONG),
        ([200, 600], DropReason.TOO_LONG),
        ([100, 600], DropReason.TOO_LONG),
    ],
)
def test_check_line_counts(sizes: list[int], reason: DropReason | None) -> None:
    assert check_line_counts([_text(n) for n in sizes]) == reason


def test_licence_allowlist() -> None:
    assert is_allowed_licence("BSD-3-Clause")
    assert is_allowed_licence("Apache-2.0")
    assert not is_allowed_licence("GPL-2.0")
    assert not is_allowed_licence("NOASSERTION")
    assert not is_allowed_licence(None)


BSD3 = """Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
  c. Neither the name of SymPy nor the names of its contributors
     may be used to endorse or promote products"""

BSD2 = """Unless otherwise indicated, all code in the Sphinx project is licenced under the
two clause BSD licence below.
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met"""


@pytest.mark.parametrize(
    ("text", "spdx"),
    [
        (BSD3, "BSD-3-Clause"),
        (BSD2, "BSD-2-Clause"),
        ("Permission is hereby granted, free of charge, to any person", "MIT"),
        ("Apache License\n Version 2.0, January 2004", "Apache-2.0"),
        ("GNU GENERAL PUBLIC LICENSE Version 2", None),
        ("LICENSE AGREEMENT FOR MATPLOTLIB", None),
    ],
)
def test_detect_licence_from_text(text: str, spdx: str | None) -> None:
    assert detect_licence_from_text(text) == spdx
