"""Invariant 1: the answer key never reaches the client before submit."""

import pytest

from tests.api.conftest import SECRETS, Lab

pytestmark = pytest.mark.anyio

ANSWER_FIELDS = ("mechanism", "fix_diff", "killing_test", "upstream_id", "commit", "categor")
SEL = {"file": "pkg/core.py", "line_from": 50, "line_to": 52}


def assert_clean(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text
    for name in ANSWER_FIELDS:
        assert f'"{name}' not in text


async def test_live_session_endpoints_never_return_answer_data(lab: Lab) -> None:
    sid = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    c = lab.client
    bodies = [
        (await c.get("/api/problems")).text,
        (await c.get("/api/settings")).text,
        (await c.get("/api/sessions")).text,
        (await c.get(f"/api/sessions/{sid}")).text,
        (await c.post(f"/api/sessions/{sid}/ask", json={**SEL, "question": "What?"})).text,
        (await c.post(f"/api/sessions/{sid}/ask", json={"question": "Everything?"})).text,
        (await c.post(f"/api/sessions/{sid}/measure", json=SEL)).text,
        (await c.get(f"/api/sessions/{sid}")).text,
    ]
    for body in bodies:
        assert_clean(body)
    # What the proxy sent to the model is clean too.
    assert lab.local.calls
    for call in lab.local.calls:
        assert_clean(" ".join(m.content for m in call))


@pytest.mark.parametrize(
    "path",
    [
        "../answer.json",
        "../meta.json",
        "../tests/test_patch.diff",
        "..\\answer.json",
        "pkg/../../answer.json",
        "/etc/passwd",
    ],
)
async def test_files_outside_src_are_unreachable(lab: Lab, path: str) -> None:
    sid = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    selection = {"file": path, "line_from": 1, "line_to": 1}
    ask = await lab.client.post(f"/api/sessions/{sid}/ask", json={**selection, "question": "?"})
    assert ask.json()["refused"] and ask.json()["reason"] == "invalid_selection"
    assert_clean(ask.text)
    measure = await lab.client.post(f"/api/sessions/{sid}/measure", json=selection)
    assert measure.json()["tokens"] is None
    assert lab.local.calls == []


async def test_no_route_serves_problem_files_directly(lab: Lab) -> None:
    pid = lab.problem_ids[0]
    for url in (
        f"/problems/{pid}/v1/answer.json",
        f"/api/problems/{pid}/answer.json",
        f"/api/problems/{pid}",
        "/answer.json",
    ):
        resp = await lab.client.get(url)
        assert resp.status_code in (404, 405)
        assert_clean(resp.text)


async def test_debrief_is_closed_until_submit_then_reveals_the_key(lab: Lab) -> None:
    sid = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    before = await lab.client.get(f"/api/sessions/{sid}/debrief")
    assert before.status_code == 409 and before.json()["error"]["code"] == "not_submitted"
    assert_clean(before.text)
    regrade = await lab.client.post(f"/api/sessions/{sid}/regrade")
    assert regrade.status_code == 409  # a live session cannot be graded into revealing the key
    assert_clean((await lab.client.get(f"/api/sessions/{sid}/debrief")).text)

    await lab.client.post(f"/api/sessions/{sid}/submit", json={"findings": []})
    after = await lab.client.get(f"/api/sessions/{sid}/debrief")
    assert after.status_code == 200
    for secret in SECRETS:
        if secret != "SECRET_TEST_PATCH":  # tests/ is never served, even after submit
            assert secret in after.text  # the gate, not an empty key, kept it clean before
    assert "SECRET_TEST_PATCH" not in after.text

    # Another live session on the same problem still sees nothing.
    other = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    assert_clean((await lab.client.get(f"/api/sessions/{other}")).text)
    assert (await lab.client.get(f"/api/sessions/{other}/debrief")).status_code == 409
