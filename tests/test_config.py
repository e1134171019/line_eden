# -*- coding: utf-8 -*-

import pytest

import config


def test_env_int_uses_default_for_blank_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_INTEGER_SETTING", "  ")

    assert config._env_int("TEST_INTEGER_SETTING", 7) == 7


def test_env_int_rejects_non_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_INTEGER_SETTING", "three")

    with pytest.raises(RuntimeError, match="TEST_INTEGER_SETTING"):
        config._env_int("TEST_INTEGER_SETTING", 7)


def test_env_bool_accepts_explicit_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_BOOL_SETTING", "true")
    assert config._env_bool("TEST_BOOL_SETTING", False) is True

    monkeypatch.setenv("TEST_BOOL_SETTING", "0")
    assert config._env_bool("TEST_BOOL_SETTING", True) is False


def test_env_bool_rejects_ambiguous_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_BOOL_SETTING", "maybe")

    with pytest.raises(RuntimeError, match="TEST_BOOL_SETTING"):
        config._env_bool("TEST_BOOL_SETTING", False)


def test_validate_gemini_rejects_inconsistent_token_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "GEMINI_MODEL", "gemini-test")
    monkeypatch.setattr(config, "GEMINI_MAX_CALLS_PER_RUN", 1)
    monkeypatch.setattr(config, "GEMINI_MAX_INPUT_TOKENS_PER_RUN", 1000)
    monkeypatch.setattr(config, "GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT", 1200)
    monkeypatch.setattr(config, "GEMINI_MAX_OUTPUT_TOKENS", 200)
    monkeypatch.setattr(config, "GEMINI_MAX_PAGES_PER_DOCUMENT", 2)

    with pytest.raises(RuntimeError, match="單份 Gemini input token"):
        config.validate_gemini_settings()


def test_gemini_prompt_version_contains_page_scope() -> None:
    expected = f"pages-{config.GEMINI_MAX_PAGES_PER_DOCUMENT}"

    assert config.GEMINI_PROMPT_VERSION.endswith(expected)
