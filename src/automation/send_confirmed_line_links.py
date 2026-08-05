# -*- coding: utf-8 -*-

from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    HTTP_TIMEOUT_SECONDS,
    LINE_API_URL,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_USER_ID,
    validate_settings,
)
from src.automation.eligible_line_links import (
    USER_CONFIRMED_ELIGIBLE_LINKS,
    build_line_message,
)
from src.notifiers.line_notifier import send_text_message

MAX_LINE_TEXT_LENGTH = 4800
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")


def main() -> None:
    """不執行來源稽核，直接發送使用者已確認符合的方案連結。"""

    validate_settings()
    message = build_line_message(
        USER_CONFIRMED_ELIGIBLE_LINKS,
        checked_at=datetime.now(TAIPEI_TIMEZONE),
        max_length=MAX_LINE_TEXT_LENGTH,
        collected_count=0,
    )
    send_text_message(
        api_url=LINE_API_URL,
        channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
        user_id=LINE_USER_ID,
        text=message,
        timeout_seconds=HTTP_TIMEOUT_SECONDS,
    )
    print(message)
    print("使用者確認符合連結已傳送至 LINE。")


if __name__ == "__main__":
    main()
