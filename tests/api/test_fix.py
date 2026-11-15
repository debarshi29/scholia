"""Fixing the code: the user's patch is checked for location and syntax, then judged."""

import json

import pytest

from api.grader.fix import changed_ranges, python_syntax_error, touches_bug, unified
from corpus.patch import parse_patch
from corpus.publish import Draft, publish, register
from schema import Bug, BugCategory, Source
from tests.api.conftest import CORE, UTIL, Lab

pytestmark = pytest.mark.anyio

SRC = "".join(f"line{i}\n" for i in range(1, 21))
BUG = Bug(
    id="b1",
    file="m.py",
    lines=(10, 11),
    category=BugCategory.LOGIC,
    mechanism="Wrong value on line 10.",
    fix_diff="--- a/m.py\n+++ b/m.py\n",
)


def _edit(src: str, line: int, new: str | None, insert: bool = False) -> str:
    lines = src.splitlines(keepends=True)
    if insert:
        lines.insert(line - 1, (new or "") + "\n")
    elif new is None:
        del lines[line - 1]
    else:
        lines[line - 1] = new + "\n"
    return "".join(lines)


# ---- pure checks ----


@pytest.mark.parametrize(
    ("patched", "ranges"),
    [
        (SRC, []),
        (_edit(SRC, 10, "LINE10"), [(10, 10)]),
        (_edit(_edit(SRC, 10, "X"), 11, "Y"), [(10, 11)]),
        (_edit(SRC, 5, None), [(5, 5)]),
        (_edit(SRC, 8, "extra", insert=True), [(7, 7)]),  # anchored to the line before
        (_edit(SRC, 1, "import os", insert=True), [(1, 1)]),
        (_edit(_edit(SRC, 3, "A"), 18, "B"), [(3, 3), (18, 18)]),
    ],
)
def test_changed_ranges(patched: str, ranges: list[tuple[int, int]]) -> None:
    assert changed_ranges(SRC, patched) == ranges


@pytest.mark.parametrize(
    ("ranges", "tolerance", "expected"),
    [
        ([(10, 10)], 3, True),
        ([(14, 14)], 3, True),  # 11 + 3
        ([(15, 15)], 3, False),
        ([(7, 7)], 3, True),
        ([(6, 6)], 3, False),
        ([(15, 15)], 0, False),
        ([(1, 2), (12, 12)], 0, False),
        ([(1, 2), (11, 11)], 0, True),
        ([], 3, False),
    ],
)
def test_touches_bug(ranges: list[tuple[int, int]], tolerance: int, expected: bool) -> None:
    assert touches_bug(ranges, BUG, tolerance) is expected


def test_unified_diff_is_a_real_git_diff() -> None:
    diff = unified("pkg/m.py", SRC, _edit(SRC, 10, "LINE10"))
    assert diff.startswith("diff --git a/pkg/m.py b/pkg/m.py\n--- a/pkg/m.py\n+++ b/pkg/m.py\n")
    assert "-line10\n+LINE10\n" in diff
    [fp] = parse_patch(diff)  # the corpus parser reads it back
    assert fp.locate(SRC) == [10]
    assert unified("pkg/m.py", SRC, SRC) == ""


def test_python_syntax_error() -> None:
    assert python_syntax_error("x = 1\n") is None
    assert python_syntax_error("def f(:\n    pass\n") == "line 1: invalid syntax"


# ---- through the API ----

ON_BUG = _edit(CORE, 51, "core_line_51 = 52")
FINDING = {
    "file": "pkg/core.py",
    "line_from": 50,
    "line_to": 52,
    "category": "boundary",
    "explanation": "The bound is one short.",
    "fix": "",
}


async def _submit(lab: Lab, **report: object) -> tuple[str, dict[str, object]]:
    sid: str = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    resp = await lab.client.post(f"/api/sessions/{sid}/submit", json=report)
    assert resp.status_code == 200, resp.text
    return sid, resp.json()


async def test_fix_on_the_bug_is_checked_and_judged(lab: Lab) -> None:
    lab.judge.replies = [
        json.dumps({"mechanism": 2, "fix": 2}),  # the finding
        json.dumps({"score": 1}),  # design notes
        json.dumps({"fix": 2, "notes": "Same effect as the reference."}),  # the patch
    ]
    sid, result = await _submit(
        lab,
        findings=[FINDING],
        design_notes="Inject the bound.",
        patches=[{"file": "pkg/core.py", "content": ON_BUG}],
    )
    assert result["patches"] == 1

    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    fix = d["bugs"][0]["fix"]
    assert fix == {
        "submitted": True,
        "on_target": True,
        "syntax_error": None,
        "judge_fix": 2,
        "judge_notes": "Same effect as the reference.",
        "tests": None,
        "tests_detail": "",
    }
    [patch] = d["patches"]
    assert patch["file"] == "pkg/core.py"
    assert "-core_line_51 = 51\n+core_line_51 = 52\n" in patch["diff"]
    # The judge saw the answer key and the candidate's diff, in separate sections.
    prompt = lab.judge.calls[-1][1].content
    key, candidate = prompt.split("## CANDIDATE")
    assert "SECRET_FIX_DIFF" in key and "+core_line_51 = 52" in candidate


async def test_fix_without_a_finding_is_not_counted_as_a_miss(lab: Lab) -> None:
    lab.judge.replies = [json.dumps({"fix": 1, "notes": "Right place, incomplete."})]
    sid, _ = await _submit(lab, patches=[{"file": "pkg/core.py", "content": ON_BUG}])
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    bug = d["bugs"][0]
    assert bug["status"] == "missed" and bug["finding"] is None  # nothing was flagged
    assert bug["fix"]["on_target"] is True and bug["fix"]["judge_fix"] == 1
    stats = {s["category"]: s for s in (await lab.client.get("/api/stats")).json()}
    assert (stats["boundary"]["attempts"], stats["boundary"]["misses"]) == (1, 0)


async def test_fix_elsewhere_in_the_file_is_off_target(lab: Lab) -> None:
    elsewhere = _edit(CORE, 150, "core_line_150 = 0")
    sid, _ = await _submit(lab, patches=[{"file": "pkg/core.py", "content": elsewhere}])
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    fix = d["bugs"][0]["fix"]
    assert fix["submitted"] is True and fix["on_target"] is False
    stats = {s["category"]: s for s in (await lab.client.get("/api/stats")).json()}
    assert stats["boundary"]["misses"] == 1


async def test_edit_to_another_file_is_kept_but_is_not_a_fix_for_the_bug(lab: Lab) -> None:
    other = _edit(UTIL, 3, "util_line_3 = 0")
    sid, result = await _submit(lab, patches=[{"file": "pkg/util.py", "content": other}])
    assert result["patches"] == 1
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    assert d["bugs"][0]["fix"]["submitted"] is False
    assert [p["file"] for p in d["patches"]] == ["pkg/util.py"]
    assert lab.judge.calls == []  # nothing to judge for this bug


async def test_unchanged_file_is_not_a_patch(lab: Lab) -> None:
    sid, result = await _submit(lab, patches=[{"file": "pkg/core.py", "content": CORE}])
    assert result["patches"] == 0
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    assert d["patches"] == [] and d["bugs"][0]["fix"]["submitted"] is False


async def test_syntax_error_is_reported(lab: Lab) -> None:
    broken = _edit(CORE, 51, "core_line_51 = (52")
    sid, _ = await _submit(lab, patches=[{"file": "pkg/core.py", "content": broken}])
    fix = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()["bugs"][0]["fix"]
    assert fix["on_target"] is True and fix["syntax_error"].startswith("line 51")


async def test_judge_down_leaves_the_fix_unscored(lab: Lab) -> None:
    lab.judge.fail = True
    sid, _ = await _submit(lab, patches=[{"file": "pkg/core.py", "content": ON_BUG}])
    fix = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()["bugs"][0]["fix"]
    assert fix["on_target"] is True and fix["judge_fix"] is None


@pytest.mark.parametrize(
    ("patches", "code"),
    [
        ([{"file": "pkg/nope.py", "content": "x"}], "invalid_patch"),
        ([{"file": "../answer.json", "content": "x"}], "validation_error"),
        (
            [{"file": "pkg/core.py", "content": "a"}, {"file": "pkg/core.py", "content": "b"}],
            "validation_error",
        ),
    ],
)
async def test_invalid_patches_are_rejected(
    lab: Lab, patches: list[dict[str, str]], code: str
) -> None:
    sid = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    resp = await lab.client.post(f"/api/sessions/{sid}/submit", json={"patches": patches})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == code
    assert (await lab.client.get(f"/api/sessions/{sid}")).json()["submitted_at"] is None


async def test_regrade_keeps_one_fix_result_per_bug(lab: Lab) -> None:
    sid, _ = await _submit(lab, patches=[{"file": "pkg/core.py", "content": ON_BUG}])
    lab.judge.replies = [json.dumps({"fix": 2})]
    assert (await lab.client.post(f"/api/sessions/{sid}/regrade")).status_code == 202
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    assert d["bugs"][0]["fix"]["judge_fix"] == 2 and len(d["patches"]) == 1


# ---- running the problem's doctests on a fix (planted problems only) ----

ADDER_FIXED = (
    "\n".join(f"# padding {i}" for i in range(1, 30))
    + '''


def add(a, b):
    """
    >>> add(1, 2)
    3
    >>> add(0, 5)
    5
    """
    return a + b
'''
)
ADDER_BUGGY = ADDER_FIXED.replace("return a + b", "return a - b")


async def _planted_problem(lab: Lab) -> str:
    pub = publish(
        lab.problems,
        Draft(
            tier=2,
            source=Source.PLANTED,
            upstream_id="algo/adder.py#logic@39",
            origin_repo="TheAlgorithms/Python",
            commit="c0ffee" + "0" * 34,
            licence="MIT",
            files={"algo/adder.py": ADDER_BUGGY},
            bugs=[
                Bug(
                    id="b1",
                    file="algo/adder.py",
                    lines=(39, 39),
                    category=BugCategory.LOGIC,
                    mechanism="Subtracts instead of adding.",
                    fix_diff="--- a/algo/adder.py\n+++ b/algo/adder.py\n",
                )
            ],
        ),
    )
    await register(lab.engine, [pub])
    return pub.meta.problem_id


async def _fix_tests(lab: Lab, content: str) -> dict[str, object]:
    pid = await _planted_problem(lab)
    lab.judge.replies = [json.dumps({"fix": 2, "notes": "ok"})]
    sid = (await lab.start(problem_id=pid))["id"]
    body = {"patches": [{"file": "algo/adder.py", "content": content}]}
    assert (await lab.client.post(f"/api/sessions/{sid}/submit", json=body)).status_code == 200
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    fix: dict[str, object] = d["bugs"][0]["fix"]
    return fix


async def test_a_correct_fix_passes_the_problems_doctests(lab: Lab) -> None:
    fix = await _fix_tests(lab, ADDER_FIXED)
    assert fix["tests"] == "passed" and fix["tests_detail"] == "2 passed, 0 failed"


async def test_a_wrong_fix_fails_the_problems_doctests(lab: Lab) -> None:
    fix = await _fix_tests(lab, ADDER_BUGGY.replace("a - b", "a * b"))
    assert fix["tests"] == "failed" and "failed" in str(fix["tests_detail"])


async def test_a_fix_with_a_syntax_error_is_not_run(lab: Lab) -> None:
    fix = await _fix_tests(lab, ADDER_FIXED.replace("return a + b", "return (a + b"))
    assert fix["tests"] is None and fix["syntax_error"]


async def test_a_fix_that_hangs_is_an_error(lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("corpus.doctests.TIMEOUT_S", 1)
    hang = ADDER_FIXED.replace("return a + b", "while True:\n        pass")
    fix = await _fix_tests(lab, hang)
    assert fix["tests"] == "error"
