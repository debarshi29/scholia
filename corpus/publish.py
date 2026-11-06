"""Write a problem to ``problems/<id>/v<version>/`` and register its index row.

Published versions are immutable (invariant 8): a version directory is created
atomically and never rewritten. A fix publishes ``v<n+1>`` under the same id.

Layout::

    problems/P-0001/v1/
      src/          # served files, sanitised
      answer.json   # hidden until submit
      meta.json
      tests/        # verifying tests, never served
"""

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from api.db import ProblemRow
from corpus.text import line_count
from schema import AnswerKey, Bug, ProblemMeta, Source

_ID = re.compile(r"^P-(\d{4,})$")
_VERSION = re.compile(r"^v(\d+)$")


class PublishError(ValueError):
    pass


@dataclass(frozen=True)
class Draft:
    """Everything needed to publish one problem version. Ids are assigned on publish."""

    tier: int
    source: Source
    upstream_id: str
    origin_repo: str
    commit: str
    licence: str
    files: dict[str, str]
    """Relative path -> sanitised file text."""
    bugs: list[Bug]
    design_notes: list[str] = field(default_factory=list)
    tests: dict[str, str] = field(default_factory=dict)
    """Relative path (under ``tests/``) -> content."""


@dataclass(frozen=True)
class Published:
    path: Path
    meta: ProblemMeta
    answer: AnswerKey


def _safe_rel(rel: str) -> PurePosixPath:
    p = PurePosixPath(rel.replace("\\", "/"))
    if not rel or p.is_absolute() or ".." in p.parts:
        raise PublishError(f"unsafe relative path: {rel!r}")
    return p


def problem_ids(problems_dir: Path) -> list[str]:
    if not problems_dir.is_dir():
        return []
    return sorted(d.name for d in problems_dir.iterdir() if d.is_dir() and _ID.match(d.name))


def versions(problems_dir: Path, problem_id: str) -> list[int]:
    root = problems_dir / problem_id
    if not root.is_dir():
        return []
    found = (_VERSION.match(d.name) for d in root.iterdir() if d.is_dir())
    return sorted(int(m[1]) for m in found if m)


def next_problem_id(problems_dir: Path) -> str:
    numbers = [int(m[1]) for pid in problem_ids(problems_dir) if (m := _ID.match(pid))]
    return f"P-{max(numbers, default=0) + 1:04d}"


def load_meta(problems_dir: Path, problem_id: str, version: int) -> ProblemMeta:
    path = problems_dir / problem_id / f"v{version}" / "meta.json"
    return ProblemMeta.model_validate_json(path.read_text(encoding="utf-8"))


def load_answer(problems_dir: Path, problem_id: str, version: int) -> AnswerKey:
    path = problems_dir / problem_id / f"v{version}" / "answer.json"
    return AnswerKey.model_validate_json(path.read_text(encoding="utf-8"))


def find_by_upstream(problems_dir: Path, source: Source, upstream_id: str) -> str | None:
    """Problem id already published for this dataset instance, if any."""
    for pid in problem_ids(problems_dir):
        vs = versions(problems_dir, pid)
        if vs:
            meta = load_meta(problems_dir, pid, vs[-1])
            if meta.source == source and meta.upstream_id == upstream_id:
                return pid
    return None


def _validate(draft: Draft) -> None:
    if not draft.files:
        raise PublishError("draft has no files")
    for rel in [*draft.files, *draft.tests]:
        _safe_rel(rel)
    for bug in draft.bugs:
        if bug.file not in draft.files:
            raise PublishError(f"bug {bug.id} refers to unknown file {bug.file}")
        n = line_count(draft.files[bug.file])
        if bug.lines[1] > n:
            raise PublishError(f"bug {bug.id} lines {bug.lines} exceed {bug.file} ({n} lines)")


def publish(problems_dir: Path, draft: Draft, problem_id: str | None = None) -> Published:
    """Publish ``draft`` as a new problem, or as the next version of ``problem_id``."""
    _validate(draft)
    problems_dir.mkdir(parents=True, exist_ok=True)
    pid = problem_id or next_problem_id(problems_dir)
    if problem_id is not None and not versions(problems_dir, problem_id):
        raise PublishError(f"{problem_id} does not exist; omit problem_id to create it")
    version = max(versions(problems_dir, pid), default=0) + 1

    meta = ProblemMeta(
        problem_id=pid,
        version=version,
        tier=draft.tier,
        source=draft.source,
        upstream_id=draft.upstream_id,
        origin_repo=draft.origin_repo,
        commit=draft.commit,
        licence=draft.licence,
        line_count=sum(line_count(t) for t in draft.files.values()),
        file_count=len(draft.files),
    )
    answer = AnswerKey(
        problem_id=pid, version=version, bugs=draft.bugs, design_notes=draft.design_notes
    )

    final = problems_dir / pid / f"v{version}"
    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{pid}-v{version}-", dir=problems_dir))
    try:
        for rel, text in draft.files.items():
            _write(staging / "src" / _safe_rel(rel), text)
        for rel, text in draft.tests.items():
            _write(staging / "tests" / _safe_rel(rel), text)
        _write(staging / "meta.json", meta.model_dump_json(indent=2) + "\n")
        _write(staging / "answer.json", answer.model_dump_json(indent=2) + "\n")
        if final.exists():
            raise PublishError(f"{final} already exists; published versions are immutable")
        os.replace(staging, final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return Published(path=final, meta=meta, answer=answer)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" keeps the file's own line endings byte-for-byte.
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def index_row(published: Published) -> ProblemRow:
    meta, answer = published.meta, published.answer
    return ProblemRow(
        id=meta.problem_id,
        version=meta.version,
        tier=meta.tier,
        source=meta.source,
        files=sorted(_src_files(published.path)),
        lines=meta.line_count,
        categories=sorted({b.category for b in answer.bugs}),
    )


def _src_files(version_dir: Path) -> set[str]:
    src = version_dir / "src"
    return {p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_file()}


def scan(problems_dir: Path) -> list[Published]:
    """Every published version on disk, in id/version order."""
    out: list[Published] = []
    for pid in problem_ids(problems_dir):
        for v in versions(problems_dir, pid):
            out.append(
                Published(
                    path=problems_dir / pid / f"v{v}",
                    meta=load_meta(problems_dir, pid, v),
                    answer=load_answer(problems_dir, pid, v),
                )
            )
    return out


async def register(engine: AsyncEngine, published: list[Published]) -> None:
    """Upsert index rows for published versions (idempotent; rows mirror immutable files)."""
    async with AsyncSession(engine) as db:
        for p in published:
            await db.merge(index_row(p))
        await db.commit()
