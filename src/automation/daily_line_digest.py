# -*- coding: utf-8 -*-

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
from main import build_full_service
from src.notifiers.line_notifier import send_text_message
from src.runtime.run_mode import RunMode
from src.services.scholarship_service import ScholarshipService, ServiceResult

MAX_LINE_TEXT_LENGTH = 4800
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")


def build_daily_message(
    result: ServiceResult,
    source_lines: list[str] | tuple[str, ...] = (),
    checked_at: datetime | None = None,
) -> str:
    local_time = checked_at or datetime.now(TAIPEI_TIMEZONE)
    lines = [
        "獎學金每日檢查完成",
        f"時間：{local_time:%Y-%m-%d %H:%M}",
        f"本次蒐集公告：{len(result.collected)}",
        f"本次符合並通知：{result.notified_count}",
        f"資格待確認：{result.review_count}（不推播）",
        f"明確不符合：{result.ineligible_count}",
        f"Gemini 生成呼叫：{result.gemini_calls}",
        "",
        result.message,
    ]
    if source_lines:
        lines.extend(["", "來源狀態：", *(f"- {line}" for line in source_lines)])
    if result.notified_count == 0:
        lines.extend(["", "今天沒有新的明確符合公告。"])
    return "\n".join(lines)[:MAX_LINE_TEXT_LENGTH]


def build_failure_message(error: Exception, checked_at: datetime | None = None) -> str:
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
    validate_settings()
    validate_gemini_settings()
    service = build_full_service(RunMode.LIVE, use_gemini=True)
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
