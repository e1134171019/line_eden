# -*- coding: utf-8 -*-

import json
from typing import Any

import pytest

from src.automation import line_transport_test


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_line_transport_test_uses_env_and_stdlib(monkeypatch: Any) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "token-value")
    monkeypatch.setenv("LINE_USER_ID", "user-id")

    def fake_urlopen(request: object, timeout: float) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(line_transport_test.urllib.request, "urlopen", fake_urlopen)

    line_transport_test.main()

    request = captured["request"]
    assert request.full_url == line_transport_test.LINE_API_URL
    assert request.get_header("Authorization") == "Bearer token-value"
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["to"] == "user-id"
    assert payload["messages"][0]["text"] == line_transport_test.LINE_TRANSPORT_TEST_MESSAGE
    assert captured["timeout"] == line_transport_test.HTTP_TIMEOUT_SECONDS


def test_line_transport_test_rejects_missing_secret(monkeypatch: Any) -> None:
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("LINE_USER_ID", "user-id")

    with pytest.raises(RuntimeError, match="LINE_CHANNEL_ACCESS_TOKEN"):
        line_transport_test.main()
