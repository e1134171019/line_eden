# -*- coding: utf-8 -*-

from collections.abc import Iterable
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    HTTP_TIMEOUT_SECONDS,
    LINE_API_URL,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_USER_ID,
    validate_gemini_settings,
    validate_settings,
)
from main import build_service
from src.automation.eligible_line_links import (
    EligibleLink,
    USER_CONFIRMED_ELIGIBLE_LINKS,
    build_line_message,
    links_from_scholarships,
    merge_links,
)
from src.notifiers.line_notifier import send_text_message
from src.runtime.run_mode import RunMode
from src.services.scholarship_service import ScholarshipService, ServiceResult

MAX_LINE_TEXT_LENGTH = 4800
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")


def build_daily_message(
    result: ServiceResult,
    source_lines: list[str] | tuple[str, ...] = (),
    checked_at: datetime | None = None,
    confirmed_links: Iterable[EligibleLink] = USER_CONFIRMED_ELIGIBLE_LINKS,
) -> str:
    """建立每日固定 LINE 摘要，只顯示統計、符合方案名稱與連結。"""

    # 來源診斷保留在 GitHub Actions 日誌與 artifact，不送到 LINE。
    _ = source_lines
    local_time = checked_at or datetime.now(TAIPEI_TIMEZONE)
    links = merge_links(
        confirmed_links,
        links_from_scholarships(result.pending_items),
    )
    return build_line_message(
        links,
        checked_at=local_time,
        max_length=MAX_LINE_TEXT_LENGTH,
        collected_count=len(result.collected),
    )


def build_failure_message(error: Exception, checked_at: datetime | None = None) -> str:
    """建立每日執行失敗通知，避免排程壞掉時完全靜默。"""
    local_time = checked_at or datetime.now(TAIPEI_TIMEZONE)
    reason = " ".join(str(error).split())[:800] or type(error).__name__
    return (
        "獎學金每日檢查失敗\n"
        f"時間：{local_time:%Y-%m-%d %H:%M}\n"
        f"錯誤：{reason}\n"
        "GitHub Actions 已標記失敗，請檢查執行紀錄。"
    )[:MAX_LINE_TEXT_LENGTH]


def _source_summary_lines(service: ScholarshipService) -> list[str]:
    summary = getattr(service.collector, "source_summary_lines", None)
    if not callable(summary):
        return []
    return list(summary())


def _send(text: str) -> None:
    send_text_message(
        api_url=LINE_API_URL,
        channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
        user_id=LINE_USER_ID,
        text=text,
        timeout_seconds=HTTP_TIMEOUT_SECONDS,
    )


def main() -> None:
    """執行正式檢查並固定傳送每日完成或失敗通知。"""
    validate_settings()
    validate_gemini_settings()
    service = build_service(mode=RunMode.DAILY, use_gemini=True)
    try:
        result = service.run(dry_run=False)
    except Exception as error:
        _send(build_failure_message(error))
        raise
    message = build_daily_message(result, _source_summary_lines(service))
    _send(message)
    print(message)
    print("每日 LINE 摘要已送出。")


if __name__ == "__main__":
    main()
