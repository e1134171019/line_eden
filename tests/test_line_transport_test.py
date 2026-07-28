# -*- coding: utf-8 -*-

from typing import Any

import src.automation.line_transport_test as transport


def test_line_transport_test_uses_local_message(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []
    validation_calls: list[str] = []

    monkeypatch.setattr(
        transport,
        "validate_settings",
        lambda: validation_calls.append("validated"),
    )
    monkeypatch.setattr(
        transport,
        "send_text_message",
        lambda **kwargs: calls.append(kwargs),
    )

    transport.main()

    assert validation_calls == ["validated"]
    assert len(calls) == 1
    assert calls[0]["text"] == transport.LINE_TRANSPORT_TEST_MESSAGE
    assert "雲端測試" in calls[0]["text"]
