"""Debrief endpoint: a full session through the HTTP API with a scripted judge."""

import json

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db import SessionRow
from tests.api.conftest import Lab

pytestmark = pytest.mark.anyio

SEL = {"file": "pkg/core.py", "line_from": 48, "line_to": 54}
ON_BUG = {
    "file": "pkg/core.py",
    "line_from": 50,
    "line_to": 52,
    "category": "boundary",
    "explanation": "The loop bound is one short.",
    "fix": "Use <= instead of <.",
}
ELSEWHERE = {**ON_BUG, "file": "pkg/util.py", "line_from": 10, "line_to": 12}


async def _play(lab: Lab, problem: int = 0) -> str:
    """Start a session, ask twice (one refusal), submit two findings and design notes."""
    sid: str = (await lab.start(problem_id=lab.problem_ids[problem]))["id"]
    await lab.client.post(f"/api/sessions/{sid}/ask", json={"question": "No selection?"})
    await lab.client.post(f"/api/sessions/{sid}/ask", json={**SEL, "question": "Is it fine?"})
    lab.judge.replies = [
        json.dumps({"mechanism": 2, "fix": 1, "notes": "Cause is right; fix is partial."}),
        json.dumps({"score": 2, "notes": "Covers the bound."}),
        json.dumps({"verdict": "wrong", "rationale": "Said the bound was fine."}),
    ]
    resp = await lab.client.post(
        f"/api/sessions/{sid}/submit",
        json={"findings": [ON_BUG, ELSEWHERE], "design_notes": "Inject the bound."},
    )
    assert resp.status_code == 200
    return sid


async def test_debrief_for_a_full_session(lab: Lab) -> None:
    sid = await _play(lab)
    resp = await lab.client.get(f"/api/sessions/{sid}/debrief")
    assert resp.status_code == 200
    d = resp.json()

    assert d["session"]["graded"] is True and d["session"]["overtime"] is False
    assert d["problem"]["upstream_id"] == "secret-upstream-1"
    assert d["problem"]["origin_repo"] == "org/repo"
    assert d["judge_model"] == "fake-judge"

    [bug] = d["bugs"]
    assert (bug["status"], bug["assisted"]) == ("found", True)
    assert (bug["judge_mechanism"], bug["judge_fix"]) == (2, 1)
    assert bug["judge_notes"] == "Cause is right; fix is partial."
    assert bug["mechanism"].startswith("SECRET_MECHANISM") and "SECRET_FIX_DIFF" in bug["fix_diff"]
    assert (bug["line_from"], bug["line_to"], bug["category"]) == (50, 52, "boundary")
    assert bug["finding"]["explanation"] == "The loop bound is one short."

    [extra] = d["extras"]
    assert extra["file"] == "pkg/util.py"

    [audit] = d["audits"]  # the refused query is not audited
    assert (audit["verdict"], audit["relied_on"]) == ("wrong", False)  # the bug was found anyway
    assert audit["reply"] == "reply from fake-qwen" and audit["line_from"] == 48
    assert audit["tokens"] > 0 and d["totals"]["q_budget"] == 12

    assert d["design"] == {
        "notes": "Inject the bound.",
        "reference": ["SECRET_DESIGN_NOTE inject the bound."],
        "score": 2,
        "rationale": "Covers the bound.",
    }
    totals = d["totals"]
    assert (totals["bugs"], totals["found"], totals["extra"], totals["missed"]) == (1, 1, 1, 0)
    assert (totals["assisted"], totals["questions_used"], totals["refusals"]) == (1, 1, 1)
    assert (totals["wrong_claims"], totals["relied_on_wrong"]) == (1, 0)
    assert totals["session_seconds"] == 3600 and 0 <= totals["seconds_used"] < 60
    assert d["stats_delta"] == [
        {
            "category": "boundary",
            "attempts_before": 0,
            "misses_before": 0,
            "attempts_after": 1,
            "misses_after": 0,
        }
    ]

    stats = {s["category"]: s for s in (await lab.client.get("/api/stats")).json()}
    assert stats["boundary"]["attempts"] == 1 and stats["boundary"]["miss_rate"] == 0.0


async def test_missed_bug_updates_the_tracker_and_the_picker_input(lab: Lab) -> None:
    sid = (await lab.start(problem_id=lab.problem_ids[1]))["id"]
    await lab.client.post(f"/api/sessions/{sid}/submit", json={"findings": []})
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    assert d["bugs"][0]["status"] == "missed" and d["bugs"][0]["finding"] is None
    assert d["totals"]["missed"] == 1
    assert d["design"]["score"] is None and "no reference design notes" in d["design"]["rationale"]
    stats = {s["category"]: s for s in (await lab.client.get("/api/stats")).json()}
    assert stats["concurrency"] == {
        "category": "concurrency",
        "attempts": 1,
        "misses": 1,
        "miss_rate": 1.0,
    }


async def test_unparseable_judge_output_shows_as_ungraded(lab: Lab) -> None:
    sid = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    await lab.client.post(f"/api/sessions/{sid}/submit", json={"findings": [ON_BUG]})
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    [bug] = d["bugs"]
    assert bug["status"] == "ungraded" and bug["judge_mechanism"] is None
    assert d["totals"]["ungraded"] == 1 and d["totals"]["found"] == 0


async def test_pending_failed_and_regrade(lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:
    sid = (await lab.start(problem_id=lab.problem_ids[0]))["id"]

    async def boom(db: object, session_id: str) -> None:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(lab.grader, "_grade", boom)
    await lab.client.post(f"/api/sessions/{sid}/submit", json={"findings": [ON_BUG]})
    failed = await lab.client.get(f"/api/sessions/{sid}/debrief")
    assert failed.status_code == 409
    assert failed.json()["error"] == {
        "code": "grading_failed",
        "message": "RuntimeError: disk on fire",
    }
    assert (await lab.client.get(f"/api/sessions/{sid}")).json()["grade_error"]

    # While grading has not finished, the debrief says so.
    async with AsyncSession(lab.engine) as db:
        row = await db.get(SessionRow, sid)
        assert row is not None
        row.grade_error = None
        db.add(row)
        await db.commit()
    pending = await lab.client.get(f"/api/sessions/{sid}/debrief")
    assert pending.status_code == 409 and pending.json()["error"]["code"] == "grading_pending"

    monkeypatch.undo()
    lab.judge.replies = [json.dumps({"mechanism": 1, "fix": 0})]
    again = await lab.client.post(f"/api/sessions/{sid}/regrade")
    assert again.status_code == 202
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    assert d["bugs"][0]["status"] == "partial"


async def test_debrief_unknown_session(lab: Lab) -> None:
    resp = await lab.client.get("/api/sessions/nope/debrief")
    assert resp.status_code == 404
