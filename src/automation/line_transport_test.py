# -*- coding: utf-8 -*-

from config import (
    HTTP_TIMEOUT_SECONDS,
    LINE_API_URL,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_USER_ID,
    validate_settings,
)
from src.notifiers.line_notifier import send_text_message

LINE_TRANSPORT_TEST_MESSAGE = "GitHub Actions 雲端測試：LINE Messaging API 傳輸成功。"


def main() -> None:
    """只驗證 LINE 傳輸；不執行獎學金蒐集或資格判斷。"""
    validate_settings()
    send_text_message(
        api_url=LINE_API_URL,
        channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
        user_id=LINE_USER_ID,
        text=LINE_TRANSPORT_TEST_MESSAGE,
        timeout_seconds=HTTP_TIMEOUT_SECONDS,
    )
    print("LINE 雲端測試通知已送出。")


if __name__ == "__main__":
    main()
