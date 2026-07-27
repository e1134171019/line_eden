# -*- coding: utf-8 -*-

from config import (
    LINE_API_URL,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_USER_ID,
    REQUEST_TIMEOUT_SECONDS,
    TEST_MESSAGE,
    validate_settings,
)
from src.notifiers.line_notifier import send_text_message


# 執行一次 LINE 文字推播測試。
def main() -> None:
    validate_settings()
    send_text_message(
        api_url=LINE_API_URL,
        channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
        user_id=LINE_USER_ID,
        text=TEST_MESSAGE,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
    )
    print("LINE 測試訊息已送出，請檢查手機 LINE。")


if __name__ == "__main__":
    main()
