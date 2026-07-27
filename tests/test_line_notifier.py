# -*- coding: utf-8 -*-

from typing import Any

import httpx

from src.notifiers.line_notifier import send_text_message

TEST_API_URL = "https://api.line.me/v2/bot/message/push"
TEST_TOKEN = "test-token"
TEST_USER_ID = "U1234567890"
TEST_TEXT = "測試訊息"
TEST_TIMEOUT_SECONDS = 10.0


class FakeResponse:
    """模擬 LINE API 成功回應。"""

    # 模擬 httpx.Response 的狀態檢查。
    def raise_for_status(self) -> None:
        return None


# 驗證推播函式送出的網址、標頭與 JSON 格式。
def test_send_text_message(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    # 攔截外部 HTTP 請求並保存呼叫參數。
    def fake_post(*args: Any, **kwargs: Any) -> FakeResponse:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    send_text_message(
        TEST_API_URL,
        TEST_TOKEN,
        TEST_USER_ID,
        TEST_TEXT,
        TEST_TIMEOUT_SECONDS,
    )

    assert captured["args"] == (TEST_API_URL,)
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer test-token"
    assert captured["kwargs"]["json"]["to"] == TEST_USER_ID
    assert captured["kwargs"]["json"]["messages"][0]["text"] == TEST_TEXT
    assert captured["kwargs"]["timeout"] == TEST_TIMEOUT_SECONDS
