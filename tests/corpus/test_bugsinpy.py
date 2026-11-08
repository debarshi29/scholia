from pathlib import Path

import pytest

from corpus.sources.bugsinpy import NO_ISSUE, parse_info, parse_tests, read_candidates, repo_slug
from schema import Source


def test_parse_info_handles_missing_trailing_newline() -> None:
    text = 'python_version="3.7.3"\npythonpath=""\nbuggy_commit_id="331d5b0"\ntest_file="t.py"'
    assert parse_info(text) == {
        "python_version": "3.7.3",
        "pythonpath": "",
        "buggy_commit_id": "331d5b0",
        "test_file": "t.py",
    }


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("https://github.com/nvbn/thefuck", "nvbn/thefuck"),
        ("https://github.com/jakubroztocil/httpie/", "jakubroztocil/httpie"),
        ("https://github.com/psf/black.git", "psf/black"),
    ],
)
def test_repo_slug(url: str, slug: str) -> None:
    assert repo_slug(url) == slug


def test_parse_tests() -> None:
    script = (
        "pytest pandas/tests/test_a.py::TestX::test_y\n"
        "python -m unittest -q tornado.test.websocket_test.WebSocketTest.test_nodelay\n"
        "\n"
        "tox -e weird\n"
    )
    assert parse_tests(script) == [
        "pandas/tests/test_a.py::TestX::test_y",
        "tornado.test.websocket_test.WebSocketTest.test_nodelay",
        "tox -e weird",
    ]


def _bug(root: Path, project: str, n: int, *, patch: bool = True) -> None:
    pdir = root / "projects" / project
    (pdir / "bugs" / str(n)).mkdir(parents=True, exist_ok=True)
    (pdir / "project.info").write_text(f'github_url="https://github.com/o/{project}"\n')
    bdir = pdir / "bugs" / str(n)
    (bdir / "bug.info").write_text(f'buggy_commit_id="c{n}"\nfixed_commit_id="f{n}"\n')
    (bdir / "run_test.sh").write_text(f"pytest tests/test_{n}.py::test_it\n")
    if patch:
        (bdir / "bug_patch.txt").write_text("diff --git a/x.py b/x.py\n")


def test_read_candidates_orders_and_skips_incomplete(tmp_path: Path) -> None:
    _bug(tmp_path, "beta", 10)
    _bug(tmp_path, "beta", 2)
    _bug(tmp_path, "Alpha", 1)
    _bug(tmp_path, "beta", 3, patch=False)
    cands = list(read_candidates(tmp_path))
    assert [c.upstream_id for c in cands] == ["Alpha-1", "beta-2", "beta-10"]
    c = cands[1]
    assert c.source is Source.BUGSINPY
    assert (c.repo, c.commit) == ("o/beta", "c2")
    assert c.failing_tests == ["tests/test_2.py::test_it"]
    assert c.issue == NO_ISSUE
