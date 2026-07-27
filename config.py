# -*- coding: utf-8 -*-

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
LINE_API_URL = "https://api.line.me/v2/bot/message/push"
REQUEST_TIMEOUT_SECONDS = 10.0
TEST_MESSAGE = "Eden 獎學金助手：LINE Messaging API 測試成功。"

load_dotenv(ENV_PATH)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv(
    "LINE_CHANNEL_ACCESS_TOKEN",
    "",
).strip()
LINE_USER_ID = os.getenv("LINE_USER_ID", "").strip()


# 驗證 LINE 推播必要的環境變數是否完整。
def validate_settings() -> None:
    missing_names = [
        name
        for name, value in (
            ("LINE_CHANNEL_ACCESS_TOKEN", LINE_CHANNEL_ACCESS_TOKEN),
            ("LINE_USER_ID", LINE_USER_ID),
        )
        if not value
    ]
    if missing_names:
        joined_names = ", ".join(missing_names)
        raise RuntimeError(f"缺少環境變數：{joined_names}")
