"""LIBRARY_TOPICS limits what the Library lists, what the picker draws and what can start."""

import pytest

from api.config import get_settings
from corpus.topics import REPO_TOPICS, Topic
from tests.api.conftest import Lab

pytestmark = pytest.mark.anyio


async def test_projects_outside_the_topics_are_not_offered(
    lab: Lab, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A session started before the filter was switched on.
    earlier = (await lab.start(problem_id=lab.problem_ids[0]))["id"]

    monkeypatch.setenv("LIBRARY_TOPICS", "ml")
    get_settings.cache_clear()  # the fixture repo "org/repo" has no topic

    assert (await lab.client.get("/api/problems")).json() == []
    by_id = await lab.client.post("/api/sessions", json={"problem_id": lab.problem_ids[0]})
    assert by_id.status_code == 404 and by_id.json()["error"]["code"] == "problem_not_found"
    picked = await lab.client.post("/api/sessions", json={})
    assert picked.status_code == 409 and picked.json()["error"]["code"] == "no_problems"

    # Hidden is not deleted: the earlier session still opens and can be submitted.
    assert (await lab.client.get(f"/api/sessions/{earlier}")).status_code == 200
    submit = await lab.client.post(f"/api/sessions/{earlier}/submit", json={"findings": []})
    assert submit.status_code == 200
    assert (await lab.client.get(f"/api/sessions/{earlier}/debrief")).status_code == 200


async def test_projects_in_the_topics_are_listed_and_picked(
    lab: Lab, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(REPO_TOPICS, "org/repo", Topic.ML)
    monkeypatch.setenv("LIBRARY_TOPICS", "ml,math")
    get_settings.cache_clear()

    cards = (await lab.client.get("/api/problems")).json()
    assert {c["id"] for c in cards} == set(lab.problem_ids)
    assert (await lab.start())["problem_id"] in lab.problem_ids
