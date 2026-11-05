import pytest

from corpus.sanitise import RemovalReason, SanitiseError, sanitise

SRC = '''\
import os  # see #12345 for context


def load(path):
    """Load a file. Refs #999 stays: docstrings are code."""
    # TODO: this is wrong when path is empty
    if path:  # FIXME handle None
        return open(path).read()
    msg = "# not a comment, gh-1234"
    return msg


def unrelated():
    # this is fine and should stay
    return 1  # keep me
'''


def test_removes_hints_and_keeps_everything_else() -> None:
    out = sanitise(SRC, bug_ranges=[(7, 8)])
    lines = out.text.splitlines()
    assert lines[0] == "import os"
    assert lines[5] == ""  # full-line TODO comment -> empty line
    assert lines[6] == "    if path:"
    # Strings and docstrings are untouched.
    assert "Refs #999" in lines[4]
    assert lines[8] == '    msg = "# not a comment, gh-1234"'
    # Comments far from the bug survive.
    assert "# this is fine and should stay" in lines[13]
    assert lines[14] == "    return 1  # keep me"
    assert [(r.line, r.reason) for r in out.removals] == [
        (1, RemovalReason.ISSUE_REF),
        (6, RemovalReason.MARKER),
        (7, RemovalReason.MARKER),
    ]


def test_line_count_is_stable() -> None:
    out = sanitise(SRC, bug_ranges=[(7, 8)])
    assert len(out.text.splitlines()) == len(SRC.splitlines())
    assert out.text.endswith("\n")


def test_fix_hint_only_near_bug() -> None:
    src = "x = 1  # broken for negatives\n" + "y = 2\n" * 10 + "z = 3  # broken too\n"
    out = sanitise(src, bug_ranges=[(1, 1)])
    assert out.text.splitlines()[0] == "x = 1"
    assert out.text.splitlines()[-1] == "z = 3  # broken too"


def test_preserves_crlf_line_endings() -> None:
    src = "a = 1  # issue 4242\r\nb = 2\r\n"
    out = sanitise(src, bug_ranges=[])
    assert out.text == "a = 1\r\nb = 2\r\n"


def test_noop_when_nothing_to_remove() -> None:
    src = "def f():\n    return 1  # plain\n"
    out = sanitise(src, bug_ranges=[(1, 2)])
    assert out.text == src
    assert out.removals == []


def test_invalid_python_raises() -> None:
    with pytest.raises(SanitiseError):
        sanitise("print 'py2'\n", bug_ranges=[])
