# -*- coding: utf-8 -*-

from typing import Any

import pytest

import config


def test_env_bool_accepts_explicit_true_and_false(monkeypatch: Any) -> None:
    monkeypatch.setenv("FLAG", "true")
    assert config._env_bool("FLAG", False) is True

    monkeypatch.setenv("FLAG", "off")
    assert config._env_bool("FLAG", True) is False


def test_env_bool_uses_default_when_missing(monkeypatch: Any) -> None:
    monkeypatch.delenv("FLAG", raising=False)
    assert config._env_bool("FLAG", True) is True


def test_env_bool_rejects_ambiguous_value(monkeypatch: Any) -> None:
    monkeypatch.setenv("FLAG", "maybe")
    with pytest.raises(RuntimeError, match="必須是 true 或 false"):
        config._env_bool("FLAG", False)
