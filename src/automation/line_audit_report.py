# -*- coding: utf-8 -*-

from config import (
    HTTP_TIMEOUT_SECONDS,
    LINE_API_URL,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_USER_ID,
    validate_gemini_settings,
    validate_settings,
)
from main import build_service
from src.evaluators.eligibility_evaluator import ELIGIBLE
from src.notifiers.line_notifier import send_text_message
from src.services.scholarship_service import AuditResult

MAX_LINE_TEXT_LENGTH = 4800
MAX_ELIGIBLE_ITEMS = 5


def build_report_message(result: AuditResult) -> str:
    """將真實稽核結果整理成單則 LINE 報告，只列明確符合項目。"""
    lines = [
        "獎學金真實檢查報告",
        "來源：龍華科技大學",
        f"稽核公告：{len(result.records)}",
        f"明確適合：{result.eligible_count}",
        f"資格待確認：{result.review_count}（不推播）",
        f"明確不符合：{result.ineligible_count}",
        f"Gemini 生成呼叫：{result.gemini_calls}",
        f"Gemini 快取命中：{result.gemini_cache_hits}",
        "",
    ]
    eligible = [
        record.item
        for record in result.records
        if record.item.eligibility_status == ELIGIBLE
    ]
    if not eligible:
        lines.append("目前沒有明確符合你背景的公告。")
    else:
        lines.append("明確符合公告：")
        for item in eligible[:MAX_ELIGIBLE_ITEMS]:
            lines.extend([
                f"- {item.published_date}｜{item.title}",
                f"  {item.eligibility_reason}",
                f"  {item.source_url}",
            ])
        remaining = len(eligible) - MAX_ELIGIBLE_ITEMS
        if remaining > 0:
            lines.append(f"另有 {remaining} 筆明確符合公告未列出。")
    return "\n".join(lines)[:MAX_LINE_TEXT_LENGTH]


def main() -> None:
    """重新稽核真實公告並傳送 LINE，不修改 baseline 或 notified_at。"""
    validate_settings()
    validate_gemini_settings()
    result = build_service(profile_required=True, use_gemini=True).audit()
    message = build_report_message(result)
    send_text_message(
        api_url=LINE_API_URL,
        channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
        user_id=LINE_USER_ID,
        text=message,
        timeout_seconds=HTTP_TIMEOUT_SECONDS,
    )
    print(message)
    print("真實檢查報告已傳送至 LINE。")


if __name__ == "__main__":
    main()
