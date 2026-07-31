# -*- coding: utf-8 -*-

import pytest

from src.ai.gemini_retry import is_transient_error, run_with_retry


class TemporaryGeminiError(RuntimeError):
    status_code = 503


def test_retry_recovers_from_transient_error() -> None:
    calls = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TemporaryGeminiError("service unavailable")
        return "ok"

    result = run_with_retry(operation, 3, 1, delays.append)

    assert result == "ok"
    assert calls == 3
    assert delays == [1, 2]


def test_retry_does_not_repeat_schema_error() -> None:
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("invalid schema")

    with pytest.raises(ValueError, match="invalid schema"):
        run_with_retry(operation, 3, 1, lambda _: None)

    assert calls == 1


def test_transient_error_recognizes_quota_and_timeout() -> None:
    assert is_transient_error(RuntimeError("429 RESOURCE_EXHAUSTED")) is True
    assert is_transient_error(TimeoutError("timed out")) is True
    assert is_transient_error(ValueError("invalid schema")) is False
