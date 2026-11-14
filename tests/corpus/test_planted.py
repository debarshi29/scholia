"""Planted bugs: mutations, doctest verification and the path through the build."""

import ast
from pathlib import Path
from typing import cast

from corpus.build import BuildLog, run
from corpus.patch import parse_patch
from corpus.repos import LicenceResolver, RepoCache
from corpus.sources.base import Candidate
from corpus.sources.planted import MIN_LINES, doctest_result, fix_patch, mutations
from schema import Source
from tests.corpus.test_build import FakeClassifier, FakeLicences, FakeRepos

SRC = '''def largest(xs):
    """
    >>> largest([1, 5, 2])
    5
    >>> largest([3])
    3
    >>> largest([2, 2, 1])
    2
    """
    best = xs[0]
    for x in xs:
        if x > best:
            best = x
    return best


def total(a, b):
    """
    >>> total(1, 2)
    3
    """
    return a + b
'''


def test_mutations_all_parse_and_differ_by_one_edit() -> None:
    muts = mutations(SRC)
    assert muts
    for m in muts:
        ast.parse(m.text)
        assert m.text != SRC
        pairs = zip(SRC.split("\n"), m.text.split("\n"), strict=True)
        changed = [i for i, (a, b) in enumerate(pairs) if a != b]
        assert changed == [m.line - 1]


def test_mutations_flip_the_comparison_and_the_operator() -> None:
    texts = {m.text for m in mutations(SRC)}
    assert SRC.replace("x > best", "x >= best") in texts
    assert SRC.replace("return a + b", "return a - b") in texts


def test_mutations_of_broken_source_is_empty() -> None:
    assert mutations("def f(:\n") == []


def test_doctest_result_counts_passing_and_failing() -> None:
    assert doctest_result("m.py", SRC) == (4, 0)
    broken = SRC.replace("return a + b", "return a - b")
    assert doctest_result("m.py", broken) == (3, 1)


def test_doctest_result_is_none_when_the_file_cannot_run() -> None:
    assert doctest_result("m.py", "import not_a_real_module_xyz\n") is None


def test_fix_patch_is_a_git_diff_the_corpus_parser_reads_back() -> None:
    buggy = SRC.replace("return a + b", "return a - b")
    [fp] = parse_patch(fix_patch("pkg/m.py", buggy, SRC))
    assert fp.path == "pkg/m.py"
    assert fp.changed_regions(buggy) == [(22, 22)]


def _planted(path: str, buggy: str, clean: str) -> Candidate:
    return Candidate(
        source=Source.PLANTED,
        upstream_id=f"{path}#logic@22",
        repo="thealgorithms/python",
        commit="c0ffee",
        patch=fix_patch(path, buggy, clean),
        issue="1 of 4 doctests fail.",
        failing_tests=[f"python -m doctest {path}"],
        buggy_files={path: buggy},
        min_lines=10,
    )


def test_build_publishes_the_buggy_text_with_the_reverse_mutation_as_the_key(
    tmp_path: Path,
) -> None:
    buggy = SRC.replace("return a + b", "return a - b")
    log = BuildLog(source="planted", tier=2, limit=5, dry_run=False)
    [pub] = run(
        [_planted("algo/m.py", buggy, SRC)],
        build_log=log,
        problems_dir=tmp_path / "problems",
        repos=cast(RepoCache, FakeRepos({})),  # the buggy text is not read from the repo
        licences=cast(LicenceResolver, FakeLicences({"thealgorithms/python": "MIT"})),
        classifier=FakeClassifier(),
    )
    served = (pub.path / "src" / "algo" / "m.py").read_text(encoding="utf-8")
    assert "return a - b" in served and "return a + b" not in served
    assert log.kept and not log.dropped


def test_short_files_are_dropped_unless_the_source_lowers_the_minimum(tmp_path: Path) -> None:
    buggy = SRC.replace("return a + b", "return a - b")
    cand = _planted("algo/m.py", buggy, SRC)
    log = BuildLog(source="planted", tier=2, limit=5, dry_run=True)
    run(
        [Candidate(**{**cand.__dict__, "min_lines": None})],
        build_log=log,
        problems_dir=tmp_path / "problems",
        repos=cast(RepoCache, FakeRepos({})),
        licences=cast(LicenceResolver, FakeLicences({"thealgorithms/python": "MIT"})),
        classifier=None,
    )
    assert [d["reason"] for d in log.dropped] == ["too_short"]
    assert MIN_LINES < 150
