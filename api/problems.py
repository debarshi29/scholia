"""Read-only access to published problems for the API.

Only ``src/`` and ``meta.json`` are reachable from here. ``answer.json`` and ``tests/``
are deliberately not exposed (invariant 1); paths that resolve outside ``src/`` are
rejected, so ``../answer.json`` and symlink tricks fail.
"""

import asyncio
from pathlib import Path, PurePosixPath

from corpus.text import split_lines
from schema import ProblemMeta

_META_CACHE: dict[str, ProblemMeta] = {}


class ProblemFileError(LookupError):
    pass


class ProblemStore:
    def __init__(self, problems_dir: Path) -> None:
        self.root = problems_dir

    def _version_dir(self, problem_id: str, version: int) -> Path:
        d = self.root / problem_id / f"v{version}"
        if PurePosixPath(problem_id).name != problem_id or not d.is_dir():
            raise ProblemFileError(f"{problem_id} v{version} not found")
        return d

    def _src_path(self, problem_id: str, version: int, rel: str) -> Path:
        src = (self._version_dir(problem_id, version) / "src").resolve()
        candidate = (src / rel).resolve()
        if not candidate.is_relative_to(src) or not candidate.is_file():
            raise ProblemFileError(f"no such source file: {rel!r}")
        return candidate

    async def meta(self, problem_id: str, version: int) -> ProblemMeta:
        path = self._version_dir(problem_id, version) / "meta.json"
        key = str(path.resolve())
        if key not in _META_CACHE:  # published versions never change, so this is safe
            text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            _META_CACHE[key] = ProblemMeta.model_validate_json(text)
        return _META_CACHE[key]

    async def src_files(self, problem_id: str, version: int) -> list[str]:
        src = self._version_dir(problem_id, version) / "src"

        def walk() -> list[str]:
            return sorted(p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_file())

        return await asyncio.to_thread(walk)

    async def read_src(self, problem_id: str, version: int, rel: str) -> str:
        path = self._src_path(problem_id, version, rel)
        return await asyncio.to_thread(path.read_text, encoding="utf-8")

    async def read_src_lines(self, problem_id: str, version: int, rel: str) -> list[str]:
        """Lines split on ``\\n`` only, matching git, the answer key and the editor."""
        return split_lines(await self.read_src(problem_id, version, rel))
