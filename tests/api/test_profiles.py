"""Local profiles: separate history, stats and defaults, with no login."""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from api.db import init_db, make_engine
from tests.api.conftest import Lab

pytestmark = pytest.mark.anyio


async def _create(lab: Lab, name: str, **body: object) -> dict[str, Any]:
    resp = await lab.client.post("/api/profiles", json={"name": name, **body})
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _as(profile: dict[str, Any]) -> dict[str, str]:
    return {"X-Profile": profile["id"]}


async def test_the_default_profile_exists(lab: Lab) -> None:
    [p] = (await lab.client.get("/api/profiles")).json()
    assert (p["id"], p["name"], p["is_default"]) == ("default", "Default", True)


async def test_create_rename_and_name_rules(lab: Lab) -> None:
    ada = await _create(lab, "  Ada ")
    assert ada["name"] == "Ada" and not ada["is_default"]
    dup = await lab.client.post("/api/profiles", json={"name": "ada"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "profile_name_taken"
    assert (await lab.client.post("/api/profiles", json={"name": "  "})).status_code == 422

    renamed = await lab.client.patch(f"/api/profiles/{ada['id']}", json={"name": "Grace"})
    assert renamed.json()["name"] == "Grace"
    clash = await lab.client.patch(f"/api/profiles/{ada['id']}", json={"name": "default"})
    assert clash.status_code == 409


async def test_unknown_profile_header_is_404(lab: Lab) -> None:
    resp = await lab.client.get("/api/stats", headers={"X-Profile": "nope"})
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "profile_not_found"


async def test_sessions_and_problem_history_are_per_profile(lab: Lab) -> None:
    ada = await _create(lab, "Ada")
    pid = lab.problem_ids[0]
    resp = await lab.client.post("/api/sessions", json={"problem_id": pid}, headers=_as(ada))
    assert resp.status_code == 201

    assert len((await lab.client.get("/api/sessions", headers=_as(ada))).json()) == 1
    assert (await lab.client.get("/api/sessions")).json() == []  # the default profile's list

    def attempts(cards: list[dict[str, Any]]) -> int:
        return next(c["attempts"] for c in cards if c["id"] == pid)

    assert attempts((await lab.client.get("/api/problems", headers=_as(ada))).json()) == 1
    assert attempts((await lab.client.get("/api/problems")).json()) == 0


async def test_stats_follow_the_profile_that_played(lab: Lab) -> None:
    ada = await _create(lab, "Ada")
    pid = lab.problem_ids[0]
    sid = (
        await lab.client.post("/api/sessions", json={"problem_id": pid}, headers=_as(ada))
    ).json()["id"]
    assert (await lab.client.post(f"/api/sessions/{sid}/submit", json={})).status_code == 200

    def boundary(rows: list[dict[str, Any]]) -> tuple[int, int]:
        row = next(r for r in rows if r["category"] == "boundary")
        return row["attempts"], row["misses"]

    assert boundary((await lab.client.get("/api/stats", headers=_as(ada))).json()) == (1, 1)
    assert boundary((await lab.client.get("/api/stats")).json()) == (0, 0)

    reset = await lab.client.post(f"/api/profiles/{ada['id']}/reset-stats")
    assert reset.json()["attempts"] == 0 and reset.json()["sessions"] == 1  # sessions are kept
    assert boundary((await lab.client.get("/api/stats", headers=_as(ada))).json()) == (0, 0)


async def test_profile_defaults_shape_new_sessions(lab: Lab) -> None:
    ada = await _create(lab, "Ada", default_ctx_cap=2048, default_q_budget=5)
    settings = (await lab.client.get("/api/settings", headers=_as(ada))).json()
    assert (settings["default_ctx_cap"], settings["default_q_budget"]) == (2048, 5)
    assert (await lab.client.get("/api/settings")).json()["default_q_budget"] == 12

    s = await lab.client.post("/api/sessions", json={}, headers=_as(ada))
    assert (s.json()["ctx_cap"], s.json()["q_budget"], s.json()["mode"]) == (
        2048,
        5,
        "constrained",
    )
    explicit = await lab.client.post("/api/sessions", json={"q_budget": 0}, headers=_as(ada))
    assert explicit.json()["q_budget"] == 0  # a request beats the profile, even zero

    cleared = await lab.client.patch(
        f"/api/profiles/{ada['id']}", json={"default_ctx_cap": None, "default_q_budget": None}
    )
    assert (cleared.json()["default_ctx_cap"], cleared.json()["default_q_budget"]) == (None, None)


async def test_a_realistic_default_falls_back_when_gemini_is_not_configured(lab: Lab) -> None:
    ada = await _create(lab, "Ada", default_mode="realistic")
    assert (await lab.client.get("/api/settings", headers=_as(ada))).json()["default_mode"] == (
        "constrained"
    )


async def test_delete_removes_the_profile_and_its_history(lab: Lab) -> None:
    ada = await _create(lab, "Ada")
    sid = (
        await lab.client.post(
            "/api/sessions", json={"problem_id": lab.problem_ids[0]}, headers=_as(ada)
        )
    ).json()["id"]
    lab.judge.replies = [json.dumps({"mechanism": 2, "fix": 2}), json.dumps({"score": 1})]
    finding = {
        "file": "pkg/core.py",
        "line_from": 50,
        "line_to": 52,
        "category": "boundary",
        "explanation": "The bound is one short.",
        "fix": "",
    }
    # A graded session has outcomes that point at findings: deletion must handle that.
    submit = await lab.client.post(
        f"/api/sessions/{sid}/submit", json={"findings": [finding], "design_notes": "x"}
    )
    assert submit.status_code == 200

    assert (await lab.client.delete(f"/api/profiles/{ada['id']}")).status_code == 204
    assert (await lab.client.get(f"/api/profiles/{ada['id']}")).status_code == 404
    assert (await lab.client.get(f"/api/sessions/{sid}")).status_code == 404

    refused = await lab.client.delete("/api/profiles/default")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "default_profile"


async def test_existing_database_is_migrated_to_the_default_profile(tmp_path: Path) -> None:
    """A database from before profiles: sessions lack the column, stats are global."""
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE sessions (id TEXT PRIMARY KEY, problem_id TEXT, "
                    "problem_version INTEGER, mode TEXT, ctx_cap INTEGER, q_budget INTEGER, "
                    "started_at DATETIME, overtime BOOLEAN, design_notes TEXT)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO sessions VALUES ('s1', 'P-0001', 1, 'CONSTRAINED', 3072, 12, "
                    "'2026-11-01 10:00:00', 0, '')"
                )
            )
            await conn.execute(
                text(
                    "CREATE TABLE category_stats (category TEXT PRIMARY KEY, attempts INTEGER, "
                    "misses INTEGER, updated_at DATETIME)"
                )
            )
            await conn.execute(
                text("INSERT INTO category_stats VALUES ('BOUNDARY', 3, 2, '2026-11-01 10:00:00')")
            )
        await init_db(engine)
        await init_db(engine)  # idempotent
        async with engine.connect() as conn:
            profile = (await conn.execute(text("SELECT profile_id FROM sessions"))).scalar_one()
            stats = (
                await conn.execute(
                    text("SELECT profile_id, category, attempts, misses FROM profile_stats")
                )
            ).all()
        assert profile == "default"
        assert [tuple(r) for r in stats] == [("default", "BOUNDARY", 3, 2)]
    finally:
        await engine.dispose()
