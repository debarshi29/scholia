import json
from pathlib import Path
from typing import cast

import pytest

from corpus.build import BuildLog, main, run
from corpus.classify import Classification, ClassifyError, ClassifyInput
from corpus.publish import load_answer
from corpus.repos import CheckoutError, LicenceResolver, RepoCache
from corpus.sources.base import Candidate
from schema import BugCategory, CategorySource, Source

N = 200


def _source() -> str:
    lines = [f"v{i} = {i}" for i in range(1, N + 1)]
    lines[49] = "v50 = 50  # FIXME wrong bound, see #4321"
    return "\n".join(lines) + "\n"


SRC = _source()

PATCH = """\
diff --git a/pkg/core.py b/pkg/core.py
--- a/pkg/core.py
+++ b/pkg/core.py
@@ -49,3 +49,3 @@
 v49 = 49
-v50 = 50  # FIXME wrong bound, see #4321
+v50 = 51
 v51 = 51
diff --git a/pkg/tests/test_core.py b/pkg/tests/test_core.py
--- a/pkg/tests/test_core.py
+++ b/pkg/tests/test_core.py
@@ -1 +1 @@
-a
+b
"""


class FakeRepos:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files

    def resolve(self, slug: str, ref: str) -> str:
        return ref if len(ref) == 40 else ref.ljust(40, "0")

    def read_text(self, slug: str, commit: str, path: str) -> str:
        if path not in self.files:
            raise CheckoutError(path)
        return self.files[path]


class FakeLicences:
    def __init__(self, licences: dict[str, str | None]) -> None:
        self.licences = licences

    def resolve(self, slug: str, commit: str) -> str | None:
        return self.licences.get(slug)


class FakeClassifier:
    prompt_version = "classify-test"

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.seen: list[ClassifyInput] = []
        self.fail_on = fail_on or set()

    def classify(self, item: ClassifyInput) -> Classification:
        self.seen.append(item)
        if any(marker in item.issue for marker in self.fail_on):
            raise ClassifyError("bad output")
        return Classification(category=BugCategory.BOUNDARY, mechanism="Upper bound is one short.")


def _cand(uid: str, repo: str = "good/repo", patch: str = PATCH, issue: str = "x") -> Candidate:
    return Candidate(
        source=Source.SWEBENCH,
        upstream_id=uid,
        repo=repo,
        commit="c0ffee",
        patch=patch,
        issue=issue,
        test_patch="diff --git a/pkg/tests/test_core.py ...\n",
        failing_tests=["pkg/tests/test_core.py::test_bound"],
    )


def _run(
    tmp_path: Path,
    cands: list[Candidate],
    *,
    limit: int = 10,
    classifier: FakeClassifier | None = None,
    files: dict[str, str] | None = None,
    dry_run: bool = False,
) -> BuildLog:
    log = BuildLog(source="swebench", tier=0, limit=limit, dry_run=dry_run)
    run(
        cands,
        build_log=log,
        problems_dir=tmp_path / "problems",
        repos=cast(RepoCache, FakeRepos(files or {"pkg/core.py": SRC})),
        licences=cast(
            LicenceResolver, FakeLicences({"good/repo": "BSD-3-Clause", "gpl/repo": "GPL-2.0"})
        ),
        classifier=None if dry_run else (classifier or FakeClassifier()),
    )
    return log


def test_publishes_sanitised_problem_with_answer_key(tmp_path: Path) -> None:
    classifier = FakeClassifier()
    log = _run(tmp_path, [_cand("good-1")], classifier=classifier)
    assert log.kept == [{"upstream_id": "good-1", "problem_id": "P-0001"}]

    root = tmp_path / "problems" / "P-0001" / "v1"
    served = (root / "src" / "pkg" / "core.py").read_text()
    assert served.splitlines()[49] == "v50 = 50"  # hint comment stripped, line kept
    assert len(served.splitlines()) == N
    assert not (root / "src" / "pkg" / "tests").exists()  # tests are never served

    answer = load_answer(tmp_path / "problems", "P-0001", 1)
    [bug] = answer.bugs
    assert (bug.file, bug.lines) == ("pkg/core.py", (50, 50))
    assert bug.category is BugCategory.BOUNDARY
    assert bug.category_source is CategorySource.LLM
    assert bug.killing_test == "pkg/tests/test_core.py::test_bound"
    assert "test_core.py" not in bug.fix_diff

    assert json.loads((root / "tests" / "failing_tests.json").read_text()) == [
        "pkg/tests/test_core.py::test_bound"
    ]
    # The classifier saw numbered buggy context and only the source part of the fix.
    [seen] = classifier.seen
    assert "   50  v50 = 50" in seen.buggy_context
    assert "pkg/tests" not in seen.fix_diff


def test_short_commit_is_resolved_before_publish(tmp_path: Path) -> None:
    cand = _cand("short-sha")
    cand = Candidate(**{**cand.__dict__, "commit": "abc1234"})
    _run(tmp_path, [cand])
    meta = json.loads((tmp_path / "problems" / "P-0001" / "v1" / "meta.json").read_text())
    assert meta["commit"] == "abc1234".ljust(40, "0")


def test_every_candidate_is_accounted_for(tmp_path: Path) -> None:
    only_tests = PATCH.split("diff --git a/pkg/tests")[0].replace("pkg/core.py", "pkg/tests/x.py")
    cands = [
        _cand("gpl", repo="gpl/repo"),
        _cand("unknown-licence", repo="mystery/repo"),
        _cand("tests-only", patch=only_tests),
        _cand("classify-fails", issue="BOOM"),
        _cand("good"),
    ]
    log = _run(tmp_path, cands, classifier=FakeClassifier(fail_on={"BOOM"}))
    reasons = {d["upstream_id"]: d["reason"] for d in log.dropped}
    assert reasons == {
        "gpl": "licence_not_allowed",
        "unknown-licence": "licence_unknown",
        "tests-only": "no_source_files",
        "classify-fails": "classify_failed",
    }
    assert [k["upstream_id"] for k in log.kept] == ["good"]
    assert log.candidates_seen == len(log.kept) + len(log.dropped) == 5


def test_fix_spread_over_several_places_is_dropped(tmp_path: Path) -> None:
    spread = (
        PATCH.split("diff --git a/pkg/tests")[0]
        + """@@ -149,3 +149,3 @@
 v149 = 149
-v150 = 150
+v150 = 151
 v151 = 151
"""
    )
    log = _run(tmp_path, [_cand("spread", patch=spread)])
    assert log.dropped[0]["reason"] == "fix_not_localised"
    assert json.loads(log.dropped[0]["detail"]) == {"pkg/core.py": [[50, 50], [150, 150]]}


def test_licence_checked_before_classifier(tmp_path: Path) -> None:
    """Invariant 7: non-allowlisted code never reaches Gemini."""
    classifier = FakeClassifier()
    _run(tmp_path, [_cand("gpl", repo="gpl/repo")], classifier=classifier)
    assert classifier.seen == []


def test_size_filter(tmp_path: Path) -> None:
    log = _run(tmp_path, [_cand("short")], files={"pkg/core.py": "x = 1\n" * 60})
    assert log.dropped[0]["reason"] == "too_short"
    assert json.loads(log.dropped[0]["detail"]) == {"pkg/core.py": 60}


def test_limit_counts_published_problems(tmp_path: Path) -> None:
    log = _run(tmp_path, [_cand(f"c{i}") for i in range(5)], limit=2)
    assert len(log.kept) == 2
    assert log.candidates_seen == 2


def test_rerun_skips_already_published(tmp_path: Path) -> None:
    _run(tmp_path, [_cand("good")])
    log = _run(tmp_path, [_cand("good")])
    assert log.dropped[0]["reason"] == "already_published"


def test_dry_run_publishes_nothing(tmp_path: Path) -> None:
    log = _run(tmp_path, [_cand("good")], dry_run=True)
    assert len(log.kept) == 1
    assert not (tmp_path / "problems").exists()


def test_build_log_written(tmp_path: Path) -> None:
    log = _run(tmp_path, [_cand("gpl", repo="gpl/repo"), _cand("good")])
    path = log.write(tmp_path / "logs")
    payload = json.loads(path.read_text())
    assert payload["summary"] == {
        "candidates": 2,
        "kept": 1,
        "dropped": {"licence_not_allowed": 1},
    }


def test_main_requires_gemini_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from api.config import get_settings

    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        assert main(["--tier", "0", "--source", "swebench", "--limit", "1"]) == 2
    finally:
        get_settings.cache_clear()
