# -*- coding: utf-8 -*-

import pytest

import config


# 空白環境變數使用程式預設值，避免 .env 留空時直接崩潰。
def test_env_int_uses_default_for_blank_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_INTEGER_SETTING", "  ")

    assert config._env_int("TEST_INTEGER_SETTING", 7) == 7


# 非整數設定會指出實際欄位名稱。
def test_env_int_rejects_non_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_INTEGER_SETTING", "three")

    with pytest.raises(RuntimeError, match="TEST_INTEGER_SETTING"):
        config._env_int("TEST_INTEGER_SETTING", 7)


# 單份文件 Token 上限不得高於整次執行上限。
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
