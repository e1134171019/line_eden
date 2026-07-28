# -*- coding: utf-8 -*-

from typing import Any

from src.automation import line_transport_test


def test_line_transport_test_validates_and_sends(monkeypatch: Any) -> None:
    calls: list[str] = []
    sent: list[dict[str, object]] = []

    monkeypatch.setattr(
        line_transport_test,
        "validate_settings",
        lambda: calls.append("validate"),
    )
    monkeypatch.setattr(
        line_transport_test,
        "send_text_message",
        lambda **kwargs: sent.append(kwargs),
    )

    line_transport_test.main()

    assert calls == ["validate"]
    assert len(sent) == 1
    assert sent[0]["text"] == line_transport_test.LINE_TRANSPORT_TEST_MESSAGE
