# -*- coding: utf-8 -*-

import main


class FakeStream:
    """記錄 reconfigure 呼叫參數的測試輸出串流。"""

    # 初始化呼叫紀錄。
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    # 模擬 TextIOWrapper.reconfigure。
    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


# 驗證 stdout 與 stderr 都改成替換不可編碼字元。
def test_configure_console_output_uses_replace_errors(monkeypatch: object) -> None:
    stdout = FakeStream()
    stderr = FakeStream()
    monkeypatch.setattr(main.sys, "stdout", stdout)
    monkeypatch.setattr(main.sys, "stderr", stderr)

    main.configure_console_output()

    assert stdout.calls == [{"errors": "replace"}]
    assert stderr.calls == [{"errors": "replace"}]
