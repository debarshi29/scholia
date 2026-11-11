"""Judge agreement tool for the M5 dogfood gate."""

import csv
import json
from pathlib import Path

import pytest

from api.grader.agreement import FIELDS, Pair, compare, export, main, read_pairs, report
from tests.api.conftest import Lab

ON_BUG = {
    "file": "pkg/core.py",
    "line_from": 50,
    "line_to": 52,
    "category": "boundary",
    "explanation": "The loop bound is one short.",
    "fix": "Use <=.",
}


def test_compare_counts_exact_and_near_agreement() -> None:
    result = compare([Pair("a", 2, 2), Pair("b", 1, 2), Pair("c", 0, 2), Pair("d", 0, 0)])
    assert (result.n, result.exact, result.within_one) == (4, 2, 3)
    assert result.exact_rate == 0.5
    assert result.mean_abs_diff == pytest.approx(0.75)
    assert [p.label for p in result.disagreements] == ["b", "c"]
    assert compare([]).exact_rate == 0.0


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({"session_id": "s" * 12, "problem_id": "P-0001", "bug_id": "b1", **row})


def test_read_pairs_skips_unscored_rows(tmp_path: Path) -> None:
    path = tmp_path / "a.csv"
    _write(
        path,
        [
            {"judge_mechanism": "2", "judge_fix": "1", "hand_mechanism": "2", "hand_fix": "2"},
            {"judge_mechanism": "", "judge_fix": "", "hand_mechanism": "1", "hand_fix": "1"},
            {"judge_mechanism": "1", "judge_fix": "0", "hand_mechanism": "", "hand_fix": ""},
        ],
    )
    mechanism, fix, skipped = read_pairs(path)
    assert [(p.judge, p.hand) for p in mechanism] == [(2, 2)]
    assert [(p.judge, p.hand) for p in fix] == [(1, 2)]
    assert skipped == 2
    text = report("fix", compare(fix))
    assert "0/1 exact (0%)" in text and "judge 1, you 2" in text


def test_invalid_hand_grade_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "a.csv"
    _write(
        path, [{"judge_mechanism": "2", "judge_fix": "1", "hand_mechanism": "3", "hand_fix": "2"}]
    )
    assert main(["check", str(path)]) == 1
    assert "hand_mechanism must be 0, 1 or 2" in capsys.readouterr().err


def test_usage_and_no_overwrite(tmp_path: Path) -> None:
    assert main([]) == 2
    existing = tmp_path / "a.csv"
    existing.write_text("mine")
    assert main(["export", str(existing)]) == 1
    assert existing.read_text() == "mine"


@pytest.mark.anyio
async def test_export_lists_matched_findings_of_graded_sessions(lab: Lab, tmp_path: Path) -> None:
    sid = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    lab.judge.replies = [json.dumps({"mechanism": 1, "fix": 2, "notes": "Vague cause."})]
    await lab.client.post(f"/api/sessions/{sid}/submit", json={"findings": [ON_BUG]})
    await lab.start(problem_id=lab.problem_ids[1])  # live session: must not appear

    out = tmp_path / "out" / "agreement.csv"
    assert await export(out) == 1
    [row] = list(csv.DictReader(out.open(encoding="utf-8")))
    assert row["session_id"] == sid and row["bug_id"] == "b1"
    assert row["key_mechanism"].startswith("SECRET_MECHANISM")
    assert row["your_explanation"] == "The loop bound is one short."
    assert (row["judge_mechanism"], row["judge_fix"]) == ("1", "2")
    assert (row["hand_mechanism"], row["hand_fix"]) == ("", "")
    assert row["prompt_version"] == "judge-finding-v1"
