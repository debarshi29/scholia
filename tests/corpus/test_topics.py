from pathlib import Path
from typing import cast

import pytest

from api.config import Settings
from corpus.build import BuildLog, run
from corpus.repos import LicenceResolver, RepoCache
from corpus.topics import REPO_TOPICS, Topic, allowed, parse_topics, topic_of
from tests.corpus.test_build import FakeClassifier, FakeLicences, FakeRepos, _cand


def test_topic_of_known_and_unknown_projects() -> None:
    assert topic_of("scikit-learn/scikit-learn") is Topic.ML
    assert topic_of("Keras-Team/Keras") is Topic.ML  # case does not matter
    assert topic_of("sympy/sympy") is Topic.MATH
    assert topic_of("pydata/xarray") is Topic.SCIENTIFIC
    assert topic_of("django/django") is Topic.WEB
    assert topic_of("jakubroztocil/httpie/") is Topic.WEB
    assert topic_of("someone/unknown") is Topic.OTHER


def test_every_listed_repo_is_lower_case() -> None:
    assert all(repo == repo.lower() for repo in REPO_TOPICS)


def test_parse_topics() -> None:
    assert parse_topics("ml, Scientific ,math") == {Topic.ML, Topic.SCIENTIFIC, Topic.MATH}
    assert parse_topics("") == frozenset()
    with pytest.raises(ValueError):
        parse_topics("ml,frontend")


def test_allowed_with_empty_set_means_everything() -> None:
    assert allowed("django/django", frozenset())
    assert not allowed("django/django", frozenset({Topic.ML}))
    assert allowed("keras-team/keras", frozenset({Topic.ML}))


def test_settings_default_keeps_ml_scientific_and_math() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.topics == {Topic.ML, Topic.SCIENTIFIC, Topic.MATH, Topic.DSA}
    assert Settings(_env_file=None, library_topics="").topics == frozenset()  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        Settings(_env_file=None, library_topics="nonsense")  # type: ignore[call-arg]


def test_build_only_examines_projects_in_the_selected_topics(tmp_path: Path) -> None:
    src = "".join(f"v{i} = {i}\n" for i in range(1, 201)).replace(
        "v50 = 50\n", "v50 = 50  # FIXME wrong bound, see #4321\n"
    )
    licences = {"scikit-learn/scikit-learn": "BSD-3-Clause", "django/django": "BSD-3-Clause"}
    cands = [
        _cand("web-1", repo="django/django"),
        _cand("ml-1", repo="scikit-learn/scikit-learn"),
        _cand("web-2", repo="django/django"),
    ]
    log = BuildLog(source="swebench", tier=0, limit=10, dry_run=False)
    run(
        cands,
        build_log=log,
        problems_dir=tmp_path / "problems",
        repos=cast(RepoCache, FakeRepos({"pkg/core.py": src})),
        licences=cast(LicenceResolver, FakeLicences(licences)),
        classifier=FakeClassifier(),
        topics=frozenset({Topic.ML}),
    )
    assert [k["upstream_id"] for k in log.kept] == ["ml-1"]
    assert (log.skipped_by_topic, log.candidates_seen) == (2, 1)
    assert log.summary()["skipped_by_topic"] == 2
