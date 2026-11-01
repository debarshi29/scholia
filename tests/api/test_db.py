from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.db import (
    CategoryStatRow,
    ProblemRow,
    QueryRow,
    SessionRow,
    init_db,
    make_engine,
)
from schema import AssistantMode, BugCategory, Source


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = make_engine(f"sqlite:///{(tmp_path / 't.db').as_posix()}")
    init_db(eng)
    yield eng
    eng.dispose()


def _problem(version: int = 1) -> ProblemRow:
    return ProblemRow(
        id="P-0001",
        version=version,
        tier=0,
        source=Source.SWEBENCH,
        files=["worker.py"],
        lines=320,
        categories=[BugCategory.CONCURRENCY],
    )


def test_all_spec_tables_exist(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) == {
        "problems",
        "sessions",
        "queries",
        "findings",
        "outcomes",
        "claim_audits",
        "category_stats",
    }


def test_problem_versions_coexist(engine: Engine) -> None:
    """Invariant 8: a fix publishes a new version alongside the old one."""
    with Session(engine) as db:
        db.add(_problem(1))
        db.add(_problem(2))
        db.commit()
        rows = db.exec(select(ProblemRow).where(ProblemRow.id == "P-0001")).all()
    assert sorted(r.version for r in rows) == [1, 2]
    assert rows[0].categories == [BugCategory.CONCURRENCY]


def test_session_must_reference_existing_problem_version(engine: Engine) -> None:
    with Session(engine) as db:
        db.add(_problem(1))
        db.commit()
        db.add(
            SessionRow(
                id="s1",
                problem_id="P-0001",
                problem_version=2,
                mode=AssistantMode.CONSTRAINED,
                ctx_cap=3072,
                q_budget=12,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_query_seq_unique_per_session(engine: Engine) -> None:
    with Session(engine) as db:
        db.add(_problem(1))
        db.add(
            SessionRow(
                id="s1",
                problem_id="P-0001",
                problem_version=1,
                mode=AssistantMode.CONSTRAINED,
                ctx_cap=3072,
                q_budget=12,
            )
        )
        db.commit()
        db.add(QueryRow(session_id="s1", seq=1, question="q", model="m", refused_reason="x"))
        db.add(QueryRow(session_id="s1", seq=1, question="q2", model="m"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_category_stats_roundtrip(engine: Engine) -> None:
    with Session(engine) as db:
        db.add(CategoryStatRow(category=BugCategory.BOUNDARY, attempts=3, misses=1))
        db.commit()
        row = db.get(CategoryStatRow, BugCategory.BOUNDARY)
    assert row is not None
    assert (row.attempts, row.misses) == (3, 1)
