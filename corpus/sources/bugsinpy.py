"""BugsInPy (https://github.com/soarsmu/BugsInPy), cloned shallowly into ``data/repos/_datasets``.

Layout checked against the repo (master @ 11c5f1e, Nov 2026)::

    projects/<project>/project.info          github_url="https://github.com/owner/name"
    projects/<project>/bugs/<n>/bug.info     buggy_commit_id, fixed_commit_id, test_file, ...
    projects/<project>/bugs/<n>/bug_patch.txt   gold patch, applies to buggy_commit_id
    projects/<project>/bugs/<n>/run_test.sh     one test command per line (pytest/unittest)

Notes:
- ``buggy_commit_id`` is sometimes abbreviated (168 of 501); the build resolves it.
- There is no issue text, so the classifier works from code and patch alone.
- The BugsInPy repo itself declares no licence. Nothing from it is served: problems
  contain upstream project code only, whose licence the build checks per project.
"""

import re
from collections.abc import Iterator
from pathlib import Path

from git import Repo

from corpus.sources.base import Candidate
from schema import Source

REPO_URL = "https://github.com/soarsmu/BugsInPy.git"
NO_ISSUE = "(No issue text is available for this bug; infer the defect from the code and fix.)"

_KV = re.compile(r'^\s*([A-Za-z_]+)\s*=\s*"(.*)"\s*$')
_GITHUB = re.compile(r"github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


def parse_info(text: str) -> dict[str, str]:
    """Parse a ``key="value"`` file (``project.info`` / ``bug.info``)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _KV.match(line)
        if m:
            out[m[1]] = m[2]
    return out


def repo_slug(github_url: str) -> str:
    m = _GITHUB.search(github_url.strip())
    if not m:
        raise ValueError(f"not a GitHub URL: {github_url!r}")
    return f"{m[1]}/{m[2]}"


def parse_tests(run_test: str) -> list[str]:
    """Test ids from ``run_test.sh``: ``pytest a.py::T::t`` -> ``a.py::T::t``,
    ``python -m unittest -q a.b.T.t`` -> ``a.b.T.t``. Unknown commands are kept verbatim."""
    tests: list[str] = []
    for raw in run_test.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "pytest" or parts[:3] == ["python", "-m", "pytest"]:
            tests.extend(p for p in parts[1:] if not p.startswith("-") and p != "pytest")
        elif "unittest" in parts:
            tests.extend(p for p in parts[parts.index("unittest") + 1 :] if not p.startswith("-"))
        else:
            tests.append(line)
    return tests


def _bug_dirs(root: Path) -> Iterator[tuple[str, Path, Path]]:
    for project in sorted((root / "projects").iterdir(), key=lambda p: p.name.lower()):
        bugs = project / "bugs"
        if not (project / "project.info").is_file() or not bugs.is_dir():
            continue
        numbered = [d for d in bugs.iterdir() if d.is_dir() and d.name.isdigit()]
        for bug in sorted(numbered, key=lambda d: int(d.name)):
            yield project.name, project / "project.info", bug


def read_candidates(root: Path) -> Iterator[Candidate]:
    for project, project_info, bug in _bug_dirs(root):
        patch_file = bug / "bug_patch.txt"
        info_file = bug / "bug.info"
        if not patch_file.is_file() or not info_file.is_file():
            continue
        pinfo = parse_info(project_info.read_text(encoding="utf-8"))
        binfo = parse_info(info_file.read_text(encoding="utf-8"))
        if "github_url" not in pinfo or "buggy_commit_id" not in binfo:
            continue
        run_test = bug / "run_test.sh"
        yield Candidate(
            source=Source.BUGSINPY,
            upstream_id=f"{project}-{bug.name}",
            repo=repo_slug(pinfo["github_url"]),
            commit=binfo["buggy_commit_id"],
            patch=patch_file.read_text(encoding="utf-8", errors="replace"),
            issue=NO_ISSUE,
            failing_tests=parse_tests(run_test.read_text(encoding="utf-8"))
            if run_test.is_file()
            else [],
        )


def ensure_clone(dest: Path) -> Path:
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        Repo.clone_from(REPO_URL, dest, depth=1)
    return dest


class BugsInPy:
    source = Source.BUGSINPY

    def __init__(self, checkout: Path) -> None:
        self.checkout = checkout

    def candidates(self) -> Iterator[Candidate]:
        yield from read_candidates(ensure_clone(self.checkout))
