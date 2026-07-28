# -*- coding: utf-8 -*-

from collections import Counter
from collections.abc import Sequence

from config import (
    HTTP_TIMEOUT_SECONDS,
    LINE_API_URL,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_USER_ID,
    validate_gemini_settings,
    validate_settings,
)
from main import build_service
from src.automation.structured_shadow_artifact import write_structured_shadow_artifacts
from src.evaluators.eligibility_evaluator import ELIGIBLE
from src.evaluators.notice_classifier import APPLICATION
from src.evaluators.runtime_safety import classify_application_period
from src.notifiers.line_notifier import send_text_message
from src.runtime.run_mode import RunMode
from src.services.scholarship_service import AuditRecord, AuditResult

MAX_LINE_TEXT_LENGTH = 4800
MAX_ELIGIBLE_ITEMS = 5


# 將五個官方來源的真實稽核與 shadow 統計整理成 LINE 報告。
def build_report_message(
    result: AuditResult,
    source_lines: Sequence[str] = (),
) -> str:
    lines = [
        "獎學金真實檢查報告",
        f"原始公告：{len(result.records)}",
        *_scope_lines(result.records),
        f"明確適合：{result.eligible_count}",
        f"資格待確認：{result.review_count}（不推播）",
        f"明確不符合：{result.ineligible_count}",
        f"Gemini 生成呼叫：{result.gemini_calls}",
        f"Gemini 快取命中：{result.gemini_cache_hits}",
        "",
        "Structured shadow：",
        f"- 已比較：{result.structured_evaluated_count}",
        f"- 與 legacy 分歧：{result.structured_changed_count}",
        f"- 預算延後：{result.structured_deferred_count}",
        f"- 抽取錯誤：{result.structured_error_count}",
    ]
    if source_lines:
        lines.extend(["", "來源狀態：", *(f"- {line}" for line in source_lines)])
    lines.extend(["", *_eligible_lines(result)])
    return "\n".join(lines)[:MAX_LINE_TEXT_LENGTH]


# 建立公告性質、獎助類別與申請期間統計。
def _scope_lines(records: list[AuditRecord]) -> list[str]:
    notice_counts = Counter(record.item.notice_kind for record in records)
    category_counts = Counter(record.item.category for record in records)
    applications = [
        record for record in records if record.item.notice_kind == APPLICATION
    ]
    period_counts = Counter(_period_status(record) for record in applications)
    return [
        f"申請型公告：{len(applications)}",
        f"非申請型公告：{len(records) - len(applications)}",
        (
            "公告類別："
            f"獎學金 {category_counts['scholarship']}／"
            f"助學金 {category_counts['student_aid']}／"
            f"補助 {category_counts['subsidy']}／"
            f"貸款 {category_counts['loan']}／"
            f"其他 {category_counts['other']}"
        ),
        (
            "申請狀態："
            f"開放 {period_counts['open']}／"
            f"尚未開始 {period_counts['upcoming']}／"
            f"已截止 {period_counts['expired']}／"
            f"期限未知 {period_counts['deadline_unknown']}"
        ),
        f"其他公告類型：{len(records) - notice_counts[APPLICATION]}",
    ]


# 建立明確符合公告清單。
def _eligible_lines(result: AuditResult) -> list[str]:
    eligible = [
        record.item
        for record in result.records
        if record.item.eligibility_status == ELIGIBLE
    ]
    if not eligible:
        return ["目前沒有明確符合你背景且仍可申請的公告。"]
    lines = ["明確符合公告："]
    for item in eligible[:MAX_ELIGIBLE_ITEMS]:
        lines.extend([
            f"- {item.published_date}｜{item.title}",
            f"  {item.eligibility_reason}",
            f"  {item.source_url}",
        ])
    remaining = len(eligible) - MAX_ELIGIBLE_ITEMS
    if remaining > 0:
        lines.append(f"另有 {remaining} 筆明確符合公告未列出。")
    return lines


# 依完整正文與主要辦法推導申請期間狀態。
def _period_status(record: AuditRecord) -> str:
    text = record.fetch_result.eligibility_text()
    return classify_application_period(text, record.item.published_date).status


def main() -> None:
    """重新稽核五個官方來源並傳送 LINE，不修改 baseline 或 notified_at。"""
    validate_settings()
    validate_gemini_settings()
    service = build_service(mode=RunMode.AUDIT, use_gemini=True)
    result = service.audit()
    csv_path, json_path = write_structured_shadow_artifacts(result)
    source_summary = getattr(service.collector, "source_summary_lines", lambda: [])()
    message = build_report_message(result, source_summary)
    send_text_message(
        api_url=LINE_API_URL,
        channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
        user_id=LINE_USER_ID,
        text=message,
        timeout_seconds=HTTP_TIMEOUT_SECONDS,
    )
    print(message)
    print(f"Structured CSV：{csv_path}")
    print(f"Structured JSON：{json_path}")
    print("真實檢查報告已傳送至 LINE。")


if __name__ == "__main__":
    main()
