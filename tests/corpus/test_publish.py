import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db import ProblemRow, init_db, make_engine
from corpus.publish import (
    Draft,
    PublishError,
    find_by_upstream,
    load_answer,
    next_problem_id,
    publish,
    register,
    scan,
)
from schema import Bug, BugCategory, CategorySource, Source

SRC = "".join(f"x{i} = {i}\n" for i in range(200))


def _draft(upstream_id: str = "psf__requests-1", **kw: object) -> Draft:
    base: dict[str, object] = dict(
        tier=0,
        source=Source.SWEBENCH,
        upstream_id=upstream_id,
        origin_repo="psf/requests",
        commit="abc123",
        licence="Apache-2.0",
        files={"requests/models.py": SRC},
        bugs=[
            Bug(
                id="b1",
                file="requests/models.py",
                lines=(10, 12),
                category=BugCategory.BOUNDARY,
                category_source=CategorySource.LLM,
                mechanism="Off by one in range end.",
                fix_diff="--- a\n+++ b\n",
                killing_test="tests/test_models.py::test_range",
            )
        ],
        tests={"test_patch.diff": "diff --git ...\n"},
    )
    base.update(kw)
    return Draft(**base)  # type: ignore[arg-type]


def test_publish_writes_layout(tmp_path: Path) -> None:
    pub = publish(tmp_path, _draft())
    root = tmp_path / "P-0001" / "v1"
    assert pub.path == root
    assert (root / "src" / "requests" / "models.py").read_text() == SRC
    assert (root / "tests" / "test_patch.diff").exists()
    meta = json.loads((root / "meta.json").read_text())
    assert meta["problem_id"] == "P-0001"
    assert meta["line_count"] == 200
    assert meta["file_count"] == 1
    answer = load_answer(tmp_path, "P-0001", 1)
    assert answer.bugs[0].category is BugCategory.BOUNDARY
    # No staging leftovers.
    assert [p.name for p in tmp_path.iterdir()] == ["P-0001"]


def test_ids_increment(tmp_path: Path) -> None:
    publish(tmp_path, _draft("a"))
    publish(tmp_path, _draft("b"))
    assert next_problem_id(tmp_path) == "P-0003"


def test_new_version_keeps_old_one(tmp_path: Path) -> None:
    """Invariant 8: a fix is a new version; v1 is untouched."""
    publish(tmp_path, _draft())
    v1_answer = (tmp_path / "P-0001" / "v1" / "answer.json").read_bytes()
    pub2 = publish(tmp_path, _draft(design_notes=["Inject the retry policy."]), "P-0001")
    assert pub2.meta.version == 2
    assert (tmp_path / "P-0001" / "v1" / "answer.json").read_bytes() == v1_answer
    assert load_answer(tmp_path, "P-0001", 2).design_notes == ["Inject the retry policy."]


def test_unknown_problem_id_rejected(tmp_path: Path) -> None:
    with pytest.raises(PublishError, match="does not exist"):
        publish(tmp_path, _draft(), "P-0042")


@pytest.mark.parametrize(
    "kw",
    [
        {"files": {}},
        {"files": {"../escape.py": SRC}},
        {"tests": {"/abs.diff": "x"}},
        {"files": {"other.py": SRC}},  # bug points at a file that is not published
    ],
)
def test_invalid_drafts_rejected(tmp_path: Path, kw: dict[str, object]) -> None:
    with pytest.raises(PublishError):
        publish(tmp_path, _draft(**kw))
    assert not (tmp_path / "P-0001").exists()


def test_bug_lines_must_fit_file(tmp_path: Path) -> None:
    with pytest.raises(PublishError, match="exceed"):
        publish(tmp_path, _draft(files={"requests/models.py": "a = 1\n" * 5}))


def test_crlf_preserved(tmp_path: Path) -> None:
    text = SRC.replace("\n", "\r\n")
    pub = publish(tmp_path, _draft(files={"requests/models.py": text}))
    assert (pub.path / "src" / "requests" / "models.py").read_bytes() == text.encode()


def test_find_by_upstream(tmp_path: Path) -> None:
    publish(tmp_path, _draft("psf__requests-7"))
    assert find_by_upstream(tmp_path, Source.SWEBENCH, "psf__requests-7") == "P-0001"
    assert find_by_upstream(tmp_path, Source.BUGSINPY, "psf__requests-7") is None
    assert find_by_upstream(tmp_path, Source.SWEBENCH, "other") is None


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(f"sqlite+aiosqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    await init_db(eng)
    yield eng
    await eng.dispose()


@pytest.mark.anyio
async def test_register_is_idempotent(tmp_path: Path, engine: AsyncEngine) -> None:
    problems = tmp_path / "problems"
    publish(problems, _draft("a"))
    publish(problems, _draft("b"))
    await register(engine, scan(problems))
    await register(engine, scan(problems))
    async with AsyncSession(engine) as db:
        rows = (await db.exec(select(ProblemRow))).all()
    assert sorted((r.id, r.version) for r in rows) == [("P-0001", 1), ("P-0002", 1)]
    assert rows[0].files == ["requests/models.py"]
    assert rows[0].categories == [BugCategory.BOUNDARY]
