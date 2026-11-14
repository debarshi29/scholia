"""Session API: library, picker, server clock (invariant 5) and report intake."""

import random
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import api.sessions
from api.db import CategoryStatRow, FindingRow, ProblemRow, SessionRow
from api.sessions import (
    EXPLORATION_FLOOR,
    ProblemCard,
    miss_rates,
    mix_projects,
    pick_problem,
    problem_weight,
)
from schema import BugCategory, Source
from tests.api.conftest import Lab

pytestmark = pytest.mark.anyio

SEL = {"file": "pkg/core.py", "line_from": 50, "line_to": 52}
FINDING = {
    "file": "pkg/core.py",
    "line_from": 49,
    "line_to": 51,
    "category": "boundary",
    "explanation": "Loop stops one short.",
    "fix": "Use <=.",
}
CARD_FIELDS = {
    "id",
    "version",
    "tier",
    "source",
    "origin_repo",
    "licence",
    "files",
    "lines",
    "attempts",
    "last_attempt_at",
    "best_found",
    "best_bugs",
    "best_seconds",
}


# ---- library ----


async def test_problems_list_has_stats_and_no_answer_data(lab: Lab) -> None:
    await lab.start(problem_id=lab.problem_ids[0])
    cards = {c["id"]: c for c in (await lab.client.get("/api/problems")).json()}
    assert set(cards) == set(lab.problem_ids)
    first, second = cards[lab.problem_ids[0]], cards[lab.problem_ids[1]]
    assert first["attempts"] == 1 and first["last_attempt_at"]
    assert second["attempts"] == 0 and second["last_attempt_at"] is None
    assert first["files"] == ["pkg/core.py", "pkg/util.py"] and first["lines"] == 360
    assert first["best_found"] is None  # started, not graded yet
    assert set(first) == CARD_FIELDS


async def test_problems_are_ordered_unattempted_first_then_by_weak_spot(lab: Lab) -> None:
    ids = lab.problem_ids  # P-0001 is a boundary bug, P-0002 a concurrency bug
    order = [c["id"] for c in (await lab.client.get("/api/problems")).json()]
    assert order == ids  # equal weights: by id

    async with AsyncSession(lab.engine) as db:
        db.add(CategoryStatRow(category=BugCategory.CONCURRENCY, attempts=4, misses=3))
        await db.commit()
    order = [c["id"] for c in (await lab.client.get("/api/problems")).json()]
    assert order == [ids[1], ids[0]]  # the weak spot comes first

    await lab.start(problem_id=ids[1])
    order = [c["id"] for c in (await lab.client.get("/api/problems")).json()]
    assert order == [ids[0], ids[1]]  # attempted problems go last


async def test_card_shows_best_graded_attempt(lab: Lab) -> None:
    pid = lab.problem_ids[0]
    missed = (await lab.start(problem_id=pid))["id"]
    await lab.client.post(f"/api/sessions/{missed}/submit", json={"findings": []})
    card = next(c for c in (await lab.client.get("/api/problems")).json() if c["id"] == pid)
    assert (card["best_found"], card["best_bugs"]) == (0, 1)

    found = (await lab.start(problem_id=pid))["id"]
    lab.judge.replies = ['{"mechanism": 2, "fix": 2}', '{"score": 1}']
    await lab.client.post(f"/api/sessions/{found}/submit", json={"findings": [FINDING]})
    card = next(c for c in (await lab.client.get("/api/problems")).json() if c["id"] == pid)
    assert (card["best_found"], card["best_bugs"]) == (1, 1)
    assert card["attempts"] == 2 and 0 <= card["best_seconds"] < 60


async def test_stats_lists_every_category(lab: Lab) -> None:
    async with AsyncSession(lab.engine) as db:
        db.add(CategoryStatRow(category=BugCategory.BOUNDARY, attempts=4, misses=1))
        await db.commit()
    stats = {s["category"]: s for s in (await lab.client.get("/api/stats")).json()}
    assert set(stats) == {c.value for c in BugCategory}
    assert stats["boundary"]["miss_rate"] == 0.25
    assert stats["logic"] == {"category": "logic", "attempts": 0, "misses": 0, "miss_rate": None}


async def test_settings_report_defaults_and_mode_availability(lab: Lab) -> None:
    s = (await lab.client.get("/api/settings")).json()
    assert (s["default_ctx_cap"], s["default_q_budget"], s["session_minutes"]) == (3072, 12, 60)
    modes = {m["mode"]: m for m in s["modes"]}
    assert modes["constrained"]["available"] is True
    assert modes["realistic"]["available"] is False  # no key in the test environment


# ---- creating sessions ----


async def test_create_uses_defaults_and_serves_src_only(lab: Lab) -> None:
    view = await lab.start(problem_id=lab.problem_ids[0])
    assert (view["mode"], view["ctx_cap"], view["q_budget"]) == ("constrained", 3072, 12)
    assert view["problem_version"] == 1
    assert [f["path"] for f in view["files"]] == ["pkg/core.py", "pkg/util.py"]
    assert view["files"][0]["content"].startswith("core_line_1 = 1\n")
    assert view["session_seconds"] == 3600 and 3590 <= view["seconds_left"] <= 3600
    assert view["questions_used"] == 0 and view["thread"] == []
    assert view["origin_repo"] == "org/repo" and view["model"] == "qwen2.5-coder:3b"


async def test_create_with_custom_settings(lab: Lab) -> None:
    view = await lab.start(problem_id=lab.problem_ids[0], ctx_cap=1024, q_budget=0)
    assert (view["ctx_cap"], view["q_budget"]) == (1024, 0)


async def test_create_errors(lab: Lab) -> None:
    resp = await lab.client.post("/api/sessions", json={"problem_id": "P-9999"})
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "problem_not_found"
    resp = await lab.client.post("/api/sessions", json={"mode": "realistic"})
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "realistic_unavailable"
    resp = await lab.client.post("/api/sessions", json={"ctx_cap": 0})
    assert resp.status_code == 422


async def test_picker_used_when_no_problem_given(lab: Lab) -> None:
    first = await lab.start()
    second = await lab.start()
    assert {first["problem_id"], second["problem_id"]} == set(lab.problem_ids)  # unattempted first
    only = await lab.start(source="bugsinpy")
    assert only["problem_id"] == lab.problem_ids[1]


async def test_get_session_restores_thread(lab: Lab) -> None:
    view = await lab.start(problem_id=lab.problem_ids[0])
    sid = view["id"]
    await lab.client.post(f"/api/sessions/{sid}/ask", json={"question": "no selection"})
    await lab.client.post(f"/api/sessions/{sid}/ask", json={**SEL, "question": "Why?"})
    again = (await lab.client.get(f"/api/sessions/{sid}")).json()
    assert again["questions_used"] == 1
    refused, answered = again["thread"]
    assert refused["refused"] and refused["reason"] == "no_selection" and refused["reply"] is None
    assert answered["reply"] == "reply from fake-qwen" and answered["line_from"] == 50
    listed = (await lab.client.get("/api/sessions")).json()
    assert [s["id"] for s in listed] == [sid]


async def test_unknown_session_404(lab: Lab) -> None:
    resp = await lab.client.get("/api/sessions/nope")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "session_not_found"


# ---- measure ----


async def test_measure_reports_tokens_without_spending_budget(lab: Lab) -> None:
    cap = lab.proxy.constrained_overhead + 120
    sid = (await lab.start(problem_id=lab.problem_ids[0], ctx_cap=cap))["id"]
    url = f"/api/sessions/{sid}/measure"
    small = (await lab.client.post(url, json=SEL)).json()
    assert small["fits"] and small["tokens"] > small["overhead"] and small["reason"] is None
    big = (await lab.client.post(url, json={**SEL, "line_from": 1, "line_to": 200})).json()
    assert not big["fits"] and big["reason"] == "over_ctx_cap"
    bad = (await lab.client.post(url, json={**SEL, "file": "../answer.json"})).json()
    assert not bad["fits"] and bad["reason"] == "invalid_selection" and bad["tokens"] is None
    assert lab.local.calls == []
    assert (await lab.client.get(f"/api/sessions/{sid}")).json()["thread"] == []


# ---- clock (invariant 5) ----


async def test_server_owns_the_clock(lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(api.sessions, "now", lambda: t0)
    # A client-supplied start time is ignored.
    view = await lab.start(problem_id=lab.problem_ids[0], started_at="2020-01-01T00:00:00Z")
    sid = view["id"]
    assert view["started_at"].startswith("2026-01-01T12:00:00")

    monkeypatch.setattr(api.sessions, "now", lambda: t0 + timedelta(minutes=45))
    assert (await lab.client.get(f"/api/sessions/{sid}")).json()["seconds_left"] == 900

    monkeypatch.setattr(api.sessions, "now", lambda: t0 + timedelta(minutes=60))
    on_time = await lab.start(problem_id=lab.problem_ids[1])
    monkeypatch.setattr(api.sessions, "now", lambda: t0 + timedelta(minutes=120))
    resp = await lab.client.post(f"/api/sessions/{on_time['id']}/submit", json={"findings": []})
    assert resp.json()["overtime"] is False  # exactly 60:00 is on time

    monkeypatch.setattr(api.sessions, "now", lambda: t0 + timedelta(minutes=60, seconds=1))
    assert (await lab.client.get(f"/api/sessions/{sid}")).json()["seconds_left"] == 0
    late = await lab.client.post(f"/api/sessions/{sid}/submit", json={"findings": [FINDING]})
    assert late.status_code == 200 and late.json()["overtime"] is True  # accepted but flagged

    # The clock stops at submit.
    monkeypatch.setattr(api.sessions, "now", lambda: t0 + timedelta(days=3))
    frozen = (await lab.client.get(f"/api/sessions/{sid}")).json()
    assert frozen["overtime"] is True and frozen["submitted_at"].startswith("2026-01-01T13:00:01")


# ---- submit ----


async def test_submit_freezes_the_report(lab: Lab) -> None:
    sid = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    body = {"findings": [FINDING], "design_notes": "Inject the bound."}
    resp = await lab.client.post(f"/api/sessions/{sid}/submit", json=body)
    assert resp.status_code == 200
    assert resp.json()["findings"] == 1 and resp.json()["overtime"] is False

    async with AsyncSession(lab.engine) as db:
        [row] = (await db.exec(select(FindingRow).where(FindingRow.session_id == sid))).all()
        session = await db.get(SessionRow, sid)
    assert (row.file, row.line_from, row.line_to) == ("pkg/core.py", 49, 51)
    assert row.category == BugCategory.BOUNDARY
    assert session is not None and session.design_notes == "Inject the bound."

    again = await lab.client.post(f"/api/sessions/{sid}/submit", json=body)
    assert again.status_code == 409 and again.json()["error"]["code"] == "session_submitted"
    ask = await lab.client.post(f"/api/sessions/{sid}/ask", json={**SEL, "question": "late"})
    assert ask.status_code == 409
    assert lab.local.calls == []


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"file": "pkg/missing.py"}, "invalid_finding"),
        ({"file": "../answer.json"}, "validation_error"),
        ({"line_to": 201}, "invalid_finding"),
        ({"line_from": 60, "line_to": 59}, "validation_error"),
        ({"category": "typo"}, "validation_error"),
        ({"explanation": ""}, "validation_error"),
        ({"surprise": 1}, "validation_error"),
    ],
)
async def test_submit_rejects_invalid_findings(
    lab: Lab, patch: dict[str, object], code: str
) -> None:
    sid = (await lab.start(problem_id=lab.problem_ids[0]))["id"]
    body = {"findings": [{**FINDING, **patch}]}
    resp = await lab.client.post(f"/api/sessions/{sid}/submit", json=body)
    assert resp.status_code == 422 and resp.json()["error"]["code"] == code
    # Nothing was frozen: the session is still live.
    assert (await lab.client.get(f"/api/sessions/{sid}")).json()["submitted_at"] is None


# ---- picker (pure) ----


def _p(pid: str, *cats: BugCategory) -> ProblemRow:
    return ProblemRow(
        id=pid,
        version=1,
        tier=0,
        source=Source.SWEBENCH,
        files=[],
        lines=200,
        categories=list(cats),
    )


def test_weight_is_floor_plus_miss_rates() -> None:
    rates = miss_rates(
        [
            CategoryStatRow(category=BugCategory.LOGIC, attempts=4, misses=3),
            CategoryStatRow(category=BugCategory.BOUNDARY, attempts=2, misses=0),
            CategoryStatRow(category=BugCategory.COMPLEXITY, attempts=0, misses=0),
        ]
    )
    assert rates == {BugCategory.LOGIC: 0.75, BugCategory.BOUNDARY: 0.0}
    assert problem_weight([BugCategory.LOGIC], rates) == pytest.approx(EXPLORATION_FLOOR + 0.75)
    assert problem_weight([BugCategory.CONCURRENCY], rates) == EXPLORATION_FLOOR  # unseen
    both = problem_weight([BugCategory.LOGIC, BugCategory.BOUNDARY], rates)
    assert both == pytest.approx(EXPLORATION_FLOOR + 0.75)


def test_picker_favours_weak_categories_but_still_explores() -> None:
    problems = [_p("P-0001", BugCategory.LOGIC), _p("P-0002", BugCategory.BOUNDARY)]
    rates = {BugCategory.LOGIC: 0.9, BugCategory.BOUNDARY: 0.0}
    rng = random.Random(7)
    picks = [pick_problem(problems, set(), rates, rng) for _ in range(2000)]
    weak = sum(p is problems[0] for p in picks)
    assert 1700 < weak < 1950  # expected share 1.0 / 1.1 = 91%; the floor keeps the rest alive


def test_picker_skips_attempted_until_none_left() -> None:
    problems = [_p("P-0001", BugCategory.LOGIC), _p("P-0002", BugCategory.LOGIC)]
    rng = random.Random(1)
    assert all(pick_problem(problems, {"P-0001"}, {}, rng) is problems[1] for _ in range(50))
    assert pick_problem(problems, {"P-0001", "P-0002"}, {}, rng) in problems
    assert pick_problem([], set(), {}, rng) is None


def _card(pid: str, repo: str) -> ProblemCard:
    return ProblemCard(
        id=pid,
        version=1,
        tier=0,
        source=Source.SWEBENCH,
        origin_repo=repo,
        licence="MIT",
        files=["a.py"],
        lines=200,
        attempts=0,
        last_attempt_at=None,
        best_found=None,
        best_bugs=None,
        best_seconds=None,
    )


def test_mix_projects_interleaves_only_within_equal_rank() -> None:
    cards = [
        _card("P-1", "a/a"),
        _card("P-2", "a/a"),
        _card("P-3", "b/b"),
        _card("P-4", "a/a"),
        _card("P-5", "c/c"),
        _card("P-6", "c/c"),
    ]
    top, rest = (False, 0.9), (False, 0.1)
    order = [c.id for c in mix_projects(cards, [top, top, top, rest, rest, rest])]
    assert order == ["P-1", "P-3", "P-2", "P-4", "P-5", "P-6"]
    assert mix_projects([], []) == []
