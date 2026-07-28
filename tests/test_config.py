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


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
def test_env_bool_accepts_true_values(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
) -> None:
    monkeypatch.setenv("TEST_BOOLEAN_SETTING", raw)

    assert config._env_bool("TEST_BOOLEAN_SETTING", False) is True


@pytest.mark.parametrize("raw", ["0", "false", "FALSE", "no", "off"])
def test_env_bool_accepts_false_values(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
) -> None:
    monkeypatch.setenv("TEST_BOOLEAN_SETTING", raw)

    assert config._env_bool("TEST_BOOLEAN_SETTING", True) is False


def test_env_bool_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_BOOLEAN_SETTING", "sometimes")

    with pytest.raises(RuntimeError, match="TEST_BOOLEAN_SETTING"):
        config._env_bool("TEST_BOOLEAN_SETTING", False)


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


def test_legacy_timeout_alias_and_test_message_are_removed() -> None:
    assert not hasattr(config, "REQUEST_TIMEOUT_SECONDS")
    assert not hasattr(config, "TEST_MESSAGE")
