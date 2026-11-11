import pytest

from corpus.classify import (
    ClassifyError,
    ClassifyInput,
    GeminiClassifier,
    load_prompt,
    numbered_context,
    render,
)
from schema import BugCategory

ITEM = ClassifyInput(issue="Range drops last item", buggy_context="1  x", fix_diff="-a\n+b\n")


def test_prompt_has_version_and_lists_every_category() -> None:
    version, text = load_prompt()
    assert version == "classify-v1"
    for cat in BugCategory:
        assert f"`{cat.value}`" in text


def test_render_contains_all_parts() -> None:
    out = render(ITEM)
    assert "Range drops last item" in out
    assert "```diff\n-a\n+b\n" in out


def test_numbered_context_marks_gaps() -> None:
    lines = [f"l{i}" for i in range(1, 101)]
    out = numbered_context(lines, [(10, 10), (80, 80)], pad=2)
    assert out.splitlines()[0] == "    8  l8"
    assert "..." in out
    assert out.splitlines()[-1] == "   82  l82"


def _classifier(monkeypatch: pytest.MonkeyPatch, replies: list[str]) -> GeminiClassifier:
    c = GeminiClassifier(api_key="test-key", model="test-model")
    it = iter(replies)
    monkeypatch.setattr(c, "_call", lambda prompt: next(it))
    return c


def test_valid_output_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _classifier(monkeypatch, ['{"category": "boundary", "mechanism": "Stops one short."}'])
    result = c.classify(ITEM)
    assert result.category is BugCategory.BOUNDARY


def test_retries_once_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _classifier(
        monkeypatch,
        ["not json", '{"category": "logic", "mechanism": "Inverted condition."}'],
    )
    assert c.classify(ITEM).category is BugCategory.LOGIC


def test_gives_up_after_one_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _classifier(monkeypatch, ['{"category": "typo", "mechanism": "xxxxxxxxxxxx"}', "{}"])
    with pytest.raises(ClassifyError):
        c.classify(ITEM)


def test_model_must_come_from_config() -> None:
    with pytest.raises(ClassifyError, match="JUDGE_MODEL"):
        GeminiClassifier(api_key="k", model="")


def test_dropped_connection_is_a_classify_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    c = GeminiClassifier(api_key="test-key", model="test-model")

    def boom(prompt: str) -> str:
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    monkeypatch.setattr(c, "_call", boom)
    with pytest.raises(ClassifyError, match="unreachable"):
        c.classify(ITEM)
