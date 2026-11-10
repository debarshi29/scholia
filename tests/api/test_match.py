"""Deterministic matcher (invariant 9): unit cases plus the hand-graded fixtures."""

import json
from pathlib import Path
from typing import Any

import pytest

from api.grader.match import BugSpan, FindingSpan, Span, match, overlap

FIXTURES = sorted((Path(__file__).parents[1] / "fixtures" / "graded").glob("*.json"))


def b(bug_id: str, start: int, end: int, file: str = "a.py") -> BugSpan:
    return BugSpan(bug_id, Span(file, start, end))


def f(finding_id: int, start: int, end: int, file: str = "a.py") -> FindingSpan:
    return FindingSpan(finding_id, Span(file, start, end))


@pytest.mark.parametrize(
    ("bug", "finding", "widen", "expected"),
    [
        ((10, 12), (10, 12), 0, 3),
        ((10, 12), (12, 20), 0, 1),
        ((10, 12), (13, 20), 0, 0),
        ((10, 12), (13, 20), 3, 3),  # widened to 7-15
        ((10, 12), (15, 15), 3, 1),
        ((10, 12), (16, 16), 3, 0),
        ((10, 12), (1, 6), 3, 0),
        ((10, 12), (1, 7), 3, 1),
        ((2, 2), (1, 1), 3, 1),  # widening stops at line 1
        ((10, 12), (1, 500), 3, 9),
    ],
)
def test_overlap(bug: tuple[int, int], finding: tuple[int, int], widen: int, expected: int) -> None:
    assert overlap(Span("a.py", *bug), Span("a.py", *finding), widen) == expected


def test_overlap_needs_same_file() -> None:
    assert overlap(Span("a.py", 1, 9), Span("b.py", 1, 9), 3) == 0
    assert overlap(Span("pkg/a.py", 1, 9), Span("pkg\\a.py", 1, 9)) == 9


def test_single_match() -> None:
    result = match([b("b1", 30, 36)], [f(0, 31, 33)], tolerance=3)
    assert (result.pairs, result.missed, result.extra) == ((("b1", 0),), (), ())


def test_tolerance_boundary() -> None:
    assert match([b("b1", 100, 100)], [f(0, 103, 110)], 3).pairs == (("b1", 0),)
    outside = match([b("b1", 100, 100)], [f(0, 104, 110)], 3)
    assert (outside.pairs, outside.missed, outside.extra) == ((), ("b1",), (0,))
    assert match([b("b1", 100, 100)], [f(0, 104, 110)], 4).pairs == (("b1", 0),)


def test_wrong_file_never_matches() -> None:
    result = match([b("b1", 10, 12)], [f(0, 10, 12, file="other.py")], 3)
    assert (result.missed, result.extra) == (("b1",), (0,))


def test_one_finding_cannot_cover_two_bugs() -> None:
    result = match([b("b1", 10, 12), b("b2", 20, 22)], [f(0, 1, 100)], 3)
    assert result.pairs == (("b1", 0),)  # equal overlap: the earlier bug wins
    assert result.missed == ("b2",)


def test_two_findings_on_one_bug_leave_one_extra() -> None:
    result = match([b("b1", 10, 20)], [f(0, 18, 30), f(1, 10, 20)], 3)
    assert result.pairs == (("b1", 1),)  # larger overlap wins
    assert result.extra == (0,)


def test_greedy_prefers_larger_overlap_across_bugs() -> None:
    bugs = [b("b1", 10, 12), b("b2", 18, 24)]
    findings = [f(0, 14, 24), f(1, 8, 10)]
    assert match(bugs, findings, 3).pairs == (("b1", 1), ("b2", 0))


def test_order_of_findings_does_not_change_pairs() -> None:
    bugs = [b("b1", 10, 12), b("b2", 18, 24)]
    one = match(bugs, [f(0, 14, 24), f(1, 8, 10)], 3)
    two = match(bugs, [f(1, 8, 10), f(0, 14, 24)], 3)
    assert set(one.pairs) == set(two.pairs)


def test_empty_inputs() -> None:
    assert match([], [], 3) == match([], [], 0)
    assert match([b("b1", 1, 2)], [], 3).missed == ("b1",)
    assert match([], [f(0, 1, 2)], 3).extra == (0,)


def test_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        Span("a.py", 5, 4)
    with pytest.raises(ValueError):
        Span("a.py", 0, 4)
    with pytest.raises(ValueError):
        match([], [], -1)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_hand_graded_fixture(path: Path) -> None:
    fx: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    bugs = [BugSpan(x["id"], Span(x["file"], *x["lines"])) for x in fx["answer"]["bugs"]]
    findings = [
        FindingSpan(i, Span(x["file"], x["line_from"], x["line_to"]))
        for i, x in enumerate(fx["report"]["findings"])
    ]
    result = match(bugs, findings, fx["tolerance"])
    expected = fx["expected"]
    assert [list(p) for p in result.pairs] == expected["pairs"]
    assert list(result.missed) == expected["missed"]
    assert list(result.extra) == expected["extra"]


def test_fixtures_exist() -> None:
    assert len(FIXTURES) >= 5
