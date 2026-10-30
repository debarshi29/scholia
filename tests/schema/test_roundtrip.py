"""Round-trip and validation tests for the shared schema (M0 done-when)."""

import json

import pytest
from pydantic import ValidationError

from schema import (
    AnswerKey,
    Bug,
    BugCategory,
    CategorySource,
    Finding,
    ProblemMeta,
    Report,
    Severity,
    Source,
)

SPEC_ANSWER_JSON = {
    "problem_id": "P-0001",
    "version": 1,
    "bugs": [
        {
            "id": "b1",
            "file": "worker.py",
            "lines": [30, 36],
            "category": "concurrency",
            "severity": "high",
            "mechanism": "Lock released only on success; an exception leaves it held.",
            "fix_diff": "--- a/worker.py\n+++ b/worker.py\n...",
            "killing_test": "tests/test_worker.py::test_retry_releases_lock",
        }
    ],
    "design_notes": ["Retry policy is hard-coded; inject it."],
}


def _bug(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = dict(SPEC_ANSWER_JSON["bugs"][0])  # type: ignore[index]
    base.update(overrides)
    return base


def test_taxonomy_matches_spec() -> None:
    assert [c.value for c in BugCategory] == [
        "logic",
        "boundary",
        "null_empty",
        "shared_mutable_state",
        "concurrency",
        "resource_leak",
        "error_handling",
        "complexity",
    ]


def test_answer_key_parses_spec_example() -> None:
    key = AnswerKey.model_validate(SPEC_ANSWER_JSON)
    bug = key.bugs[0]
    assert bug.lines == (30, 36)
    assert bug.category is BugCategory.CONCURRENCY
    assert bug.severity is Severity.HIGH
    assert bug.category_source is CategorySource.MANUAL


@pytest.mark.parametrize("model", [AnswerKey])
def test_answer_key_json_roundtrip(model: type[AnswerKey]) -> None:
    key = model.model_validate(SPEC_ANSWER_JSON)
    again = model.model_validate_json(key.model_dump_json())
    assert again == key
    # Serialised form stays compatible with the documented answer.json shape.
    dumped = json.loads(key.model_dump_json())
    assert dumped["bugs"][0]["lines"] == [30, 36]


def test_bug_defaults() -> None:
    raw = _bug()
    del raw["severity"]
    del raw["killing_test"]
    bug = Bug.model_validate({**raw, "category_source": "llm"})
    assert bug.severity is Severity.MEDIUM
    assert bug.killing_test is None
    assert bug.category_source is CategorySource.LLM


@pytest.mark.parametrize(
    "overrides",
    [
        {"lines": [36, 30]},
        {"lines": [0, 3]},
        {"category": "typo"},
        {"file": "/etc/passwd"},
        {"file": "../outside.py"},
        {"mechanism": "   "},
        {"unexpected": 1},
    ],
)
def test_bug_rejects_invalid(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Bug.model_validate(_bug(**overrides))


def test_answer_key_rejects_duplicate_bug_ids() -> None:
    raw = {**SPEC_ANSWER_JSON, "bugs": [_bug(), _bug()]}
    with pytest.raises(ValidationError, match="unique"):
        AnswerKey.model_validate(raw)


@pytest.mark.parametrize("problem_id", ["P-1", "p-0001", "0001", "P-00a1"])
def test_answer_key_rejects_bad_problem_id(problem_id: str) -> None:
    with pytest.raises(ValidationError):
        AnswerKey.model_validate({**SPEC_ANSWER_JSON, "problem_id": problem_id})


def test_answer_key_requires_a_bug() -> None:
    with pytest.raises(ValidationError):
        AnswerKey.model_validate({**SPEC_ANSWER_JSON, "bugs": []})


def test_report_roundtrip() -> None:
    report = Report(
        findings=[
            Finding(
                file="pkg/worker.py",
                line_from=31,
                line_to=33,
                category=BugCategory.CONCURRENCY,
                explanation="Lock not released when the task raises.",
                fix="Use try/finally.",
            )
        ],
        design_notes="Retry policy should be injected.",
    )
    assert Report.model_validate_json(report.model_dump_json()) == report


def test_empty_report_is_valid() -> None:
    assert Report.model_validate({}) == Report(findings=[], design_notes="")


def test_finding_rejects_reversed_range() -> None:
    with pytest.raises(ValidationError):
        Finding(
            file="a.py",
            line_from=10,
            line_to=9,
            category=BugCategory.LOGIC,
            explanation="x",
        )


def test_problem_meta_roundtrip() -> None:
    meta = ProblemMeta(
        problem_id="P-0001",
        version=1,
        tier=0,
        source=Source.SWEBENCH,
        upstream_id="psf__requests-2317",
        origin_repo="psf/requests",
        commit="091991be0da19de9108dbe5e3752917fea3d7fdc",
        licence="Apache-2.0",
        line_count=312,
        file_count=1,
    )
    assert ProblemMeta.model_validate_json(meta.model_dump_json()) == meta


def test_models_are_immutable() -> None:
    key = AnswerKey.model_validate(SPEC_ANSWER_JSON)
    with pytest.raises(ValidationError):
        key.version = 2  # type: ignore[misc]
