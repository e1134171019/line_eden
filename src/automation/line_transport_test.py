# -*- coding: utf-8 -*-

import json
import os
import urllib.request

LINE_API_URL = "https://api.line.me/v2/bot/message/push"
LINE_TRANSPORT_TEST_MESSAGE = (
    "GitHub Actions 雲端測試：Eden 獎學金助手：LINE Messaging API 測試成功。"
)
HTTP_TIMEOUT_SECONDS = 10.0


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少環境變數：{name}")
    return value


def build_request(token: str, user_id: str) -> urllib.request.Request:
    """只使用標準函式庫建立 LINE push request，不載入專案 config。"""
    payload = json.dumps(
        {
            "to": user_id,
            "messages": [{"type": "text", "text": LINE_TRANSPORT_TEST_MESSAGE}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    return urllib.request.Request(
        LINE_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )


def main() -> None:
    """明確執行一次 LINE 傳輸測試，不匯入任何專案模組。"""
    token = _required_env("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = _required_env("LINE_USER_ID")
    request = build_request(token, user_id)
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError(f"LINE API 回傳非成功狀態：{response.status}")
    print("LINE 雲端測試通知已送出")


if __name__ == "__main__":
    main()
