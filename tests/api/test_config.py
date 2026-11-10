from pathlib import Path

import pytest

from api.config import Settings


def test_defaults_match_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("DEFAULT_CTX_CAP", "DEFAULT_Q_BUDGET", "LOCAL_MODEL", "DB_PATH"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.default_ctx_cap == 3072
    assert s.default_q_budget == 12
    assert s.session_minutes == 60
    assert s.match_tolerance_lines == 3
    assert s.local_model == "qwen2.5-coder:3b"
    assert s.db_path == Path("data/scholia.db")
    assert s.gemini_api_key is None


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_CTX_CAP", "1024")
    monkeypatch.setenv("JUDGE_MODEL", "some-flash-model")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.default_ctx_cap == 1024
    assert s.judge_model == "some-flash-model"
    assert s.gemini_api_key is not None
    assert "secret" not in repr(s)


def test_rejects_non_positive_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_CTX_CAP", "0")
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_gemini_model_is_fallback_for_both_models(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("JUDGE_MODEL", "REALISTIC_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "flash-x")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert (s.judge_model, s.realistic_model) == ("flash-x", "flash-x")
    monkeypatch.setenv("JUDGE_MODEL", "judge-y")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert (s.judge_model, s.realistic_model) == ("judge-y", "flash-x")
