"""Marking an extra finding as a fair point: a personal note that changes nothing else."""

import json

import pytest

from tests.api.conftest import Lab

pytestmark = pytest.mark.anyio

ON_BUG = {
    "file": "pkg/core.py",
    "line_from": 50,
    "line_to": 52,
    "category": "boundary",
    "explanation": "The bound is one short.",
    "fix": "",
}
ELSEWHERE = {**ON_BUG, "line_from": 150, "line_to": 152, "explanation": "A fair point."}


async def _submitted(lab: Lab) -> tuple[str, dict[str, int]]:
    lab.judge.replies = [json.dumps({"mechanism": 2, "fix": 2}), json.dumps({"score": 1})]
    sid = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    body = {"findings": [ON_BUG, ELSEWHERE], "design_notes": "x"}
    assert (await lab.client.post(f"/api/sessions/{sid}/submit", json=body)).status_code == 200
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    ids = {"matched": d["bugs"][0]["finding"]["id"], "extra": d["extras"][0]["id"]}
    return sid, ids


async def _mark(lab: Lab, sid: str, fid: int, valid: bool) -> object:
    return await lab.client.post(
        f"/api/sessions/{sid}/findings/{fid}/validity", json={"valid": valid}
    )


async def test_an_extra_can_be_marked_and_unmarked(lab: Lab) -> None:
    sid, ids = await _submitted(lab)
    stats_before = (await lab.client.get("/api/stats")).json()

    resp = await _mark(lab, sid, ids["extra"], True)
    assert resp.status_code == 200 and resp.json()["marked_valid"] is True  # type: ignore[attr-defined]
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    assert d["extras"][0]["marked_valid"] is True
    assert d["bugs"][0]["status"] == "found"  # matching is untouched
    assert (await lab.client.get("/api/stats")).json() == stats_before  # so are the stats

    await _mark(lab, sid, ids["extra"], False)
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    assert d["extras"][0]["marked_valid"] is False


async def test_a_matched_finding_cannot_be_marked(lab: Lab) -> None:
    sid, ids = await _submitted(lab)
    resp = await _mark(lab, sid, ids["matched"], True)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "not_extra"  # type: ignore[attr-defined]


async def test_unknown_findings_and_live_sessions_are_refused(lab: Lab) -> None:
    sid, _ = await _submitted(lab)
    missing = await _mark(lab, sid, 99999, True)
    assert missing.status_code == 404  # type: ignore[attr-defined]

    live = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    early = await _mark(lab, live, 1, True)
    assert early.status_code == 409 and early.json()["error"]["code"] == "not_submitted"  # type: ignore[attr-defined]


async def test_a_mark_survives_a_regrade(lab: Lab) -> None:
    sid, ids = await _submitted(lab)
    await _mark(lab, sid, ids["extra"], True)
    lab.judge.replies = [json.dumps({"mechanism": 2, "fix": 2}), json.dumps({"score": 1})]
    assert (await lab.client.post(f"/api/sessions/{sid}/regrade")).status_code == 202
    d = (await lab.client.get(f"/api/sessions/{sid}/debrief")).json()
    assert d["extras"][0]["marked_valid"] is True
