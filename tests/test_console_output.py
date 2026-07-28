# -*- coding: utf-8 -*-

import pytest

import src.formatters.cli_output_formatter as output_formatter


class FakeStream:
    """記錄 reconfigure 呼叫參數的測試輸出串流。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


def test_configure_console_output_uses_replace_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = FakeStream()
    stderr = FakeStream()
    monkeypatch.setattr(output_formatter.sys, "stdout", stdout)
    monkeypatch.setattr(output_formatter.sys, "stderr", stderr)

    output_formatter.configure_console_output()

    assert stdout.calls == [{"errors": "replace"}]
    assert stderr.calls == [{"errors": "replace"}]
