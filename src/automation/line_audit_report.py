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
from src.evaluators.eligibility_evaluator import ELIGIBLE, INELIGIBLE, REVIEW
from src.evaluators.notice_classifier import APPLICATION
from src.evaluators.runtime_safety import EXPIRED, classify_application_period
from src.notifiers.line_notifier import send_text_message
from src.runtime.run_mode import RunMode
from src.services.scholarship_service import AuditRecord, AuditResult

MAX_LINE_TEXT_LENGTH = 4800
MAX_ELIGIBLE_ITEMS = 5
MAX_REVIEW_ITEMS = 5
MAX_SHADOW_CHANGED_ITEMS = 10
MAX_SHADOW_ERROR_ITEMS = 8
MAX_DETAIL_TITLE_LENGTH = 34
MAX_DETAIL_REASON_LENGTH = 82


# 將多來源真實稽核、入口過濾與 shadow 統計整理成 LINE 報告。
def build_report_message(
    result: AuditResult,
    source_lines: Sequence[str] = (),
) -> str:
    lines = [
        "獎學金真實檢查報告",
        f"本次稽核公告：{len(result.records)}",
        *_scope_lines(result.records),
        f"Gemini 生成呼叫：{result.gemini_calls}",
        f"Gemini 快取命中：{result.gemini_cache_hits}",
        "",
        "Structured shadow：",
        f"- 已比較：{result.structured_evaluated_count}",
        f"- 與 legacy 分歧：{result.structured_changed_count}",
        f"- 預算延後：{result.structured_deferred_count}",
        f"- 抽取錯誤：{result.structured_error_count}",
        *_structured_detail_lines(result.records),
    ]
    if source_lines:
        lines.extend(["", "來源狀態：", *(f"- {line}" for line in source_lines)])
    lines.extend(["", *_eligible_lines(result)])
    return "\n".join(lines)[:MAX_LINE_TEXT_LENGTH]


# 建立公告性質、獎助類別、申請期間與真正資格統計。
def _scope_lines(records: list[AuditRecord]) -> list[str]:
    notice_counts = Counter(record.item.notice_kind for record in records)
    category_counts = Counter(record.item.category for record in records)
    applications = [
        record for record in records if record.item.notice_kind == APPLICATION
    ]
    periods = {id(record): _period_status(record) for record in applications}
    period_counts = Counter(periods[id(record)] for record in applications)
    actionable = [record for record in applications if periods[id(record)] != EXPIRED]
    eligibility_counts = Counter(
        record.item.eligibility_status for record in actionable
    )
    non_application = len(records) - notice_counts[APPLICATION]
    return [
        f"申請型公告：{len(applications)}",
        f"非申請型公告：{non_application}",
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
        (
            "個人資格（未截止與期限未知）："
            f"符合 {eligibility_counts[ELIGIBLE]}／"
            f"待確認 {eligibility_counts[REVIEW]}／"
            f"硬性不符 {eligibility_counts[INELIGIBLE]}"
        ),
        f"已截止未列為個人資格不符：{period_counts['expired']}",
        f"非申請公告未列入個人資格：{non_application}",
    ]


# 列出每筆 structured 分歧與抽取錯誤，避免摘要只剩數量。
def _structured_detail_lines(records: list[AuditRecord]) -> list[str]:
    changed = [record for record in records if _is_changed(record)]
    errors = [record for record in records if _is_shadow_error(record)]
    lines: list[str] = []
    if changed:
        lines.extend(["", "Structured 分歧明細："])
        lines.extend(_changed_line(record) for record in changed[:MAX_SHADOW_CHANGED_ITEMS])
    if errors:
        lines.extend(["", "Structured 抽取錯誤："])
        lines.extend(_error_line(record) for record in errors[:MAX_SHADOW_ERROR_ITEMS])
    return lines


def _is_changed(record: AuditRecord) -> bool:
    shadow = getattr(record, "structured_shadow", None)
    return bool(shadow and shadow.changed)


def _is_shadow_error(record: AuditRecord) -> bool:
    return getattr(record, "shadow_status", "") in {"text_error", "text_cached_error"}


# 將一筆 legacy／structured 差異壓縮成單行 LINE 文字。
def _changed_line(record: AuditRecord) -> str:
    shadow = record.structured_shadow
    assert shadow is not None
    title = _short(record.item.title, MAX_DETAIL_TITLE_LENGTH)
    reason = _short(shadow.structured_reason, MAX_DETAIL_REASON_LENGTH)
    return f"- {title}：{shadow.legacy_status}→{shadow.structured_status}；{reason}"


# 將一筆 Gemini 錯誤壓縮成單行，保留實際例外訊息。
def _error_line(record: AuditRecord) -> str:
    diagnostic = record.structured_gemini_diagnostic
    title = _short(record.item.title, MAX_DETAIL_TITLE_LENGTH)
    message = diagnostic.message if diagnostic else "未提供錯誤診斷"
    return f"- {title}：{_short(message, MAX_DETAIL_REASON_LENGTH)}"


def _short(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


# 建立目前仍具申請可能且明確符合的公告清單。
def _eligible_lines(result: AuditResult) -> list[str]:
    eligible = [
        record.item
        for record in result.records
        if record.item.notice_kind == APPLICATION
        and record.item.eligibility_status == ELIGIBLE
        and _period_status(record) != EXPIRED
    ]
    if not eligible:
        return _review_fallback_lines(result)
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


def _review_fallback_lines(result: AuditResult) -> list[str]:
    """純函式：沒有明確符合項目時，仍列出可申請但待人工確認的公告。"""

    review_records = [
        record
        for record in result.records
        if record.item.notice_kind == APPLICATION
        and record.item.eligibility_status == REVIEW
        and _period_status(record) != EXPIRED
    ]
    lines = ["目前沒有明確符合你背景且仍可申請的公告。"]
    if not review_records:
        return lines
    lines.append("仍可人工確認公告：")
    for record in review_records[:MAX_REVIEW_ITEMS]:
        item = record.item
        lines.extend([
            f"- {item.published_date}｜{item.title}",
            f"  {item.eligibility_reason}",
            f"  {item.source_url}",
        ])
    remaining = len(review_records) - MAX_REVIEW_ITEMS
    if remaining > 0:
        lines.append(f"另有 {remaining} 筆待確認公告未列出。")
    return lines


# 依完整正文與主要辦法推導申請期間狀態。
def _period_status(record: AuditRecord) -> str:
    text = record.fetch_result.eligibility_text()
    return classify_application_period(text, record.item.published_date).status


def main() -> None:
    """重新稽核六個官方來源並傳送 LINE，不修改 baseline 或 notified_at。"""
    validate_settings()
    validate_gemini_settings()
    service = build_service(mode=RunMode.AUDIT, use_gemini=True)
    result = service.audit()
    csv_path, json_path = write_structured_shadow_artifacts(result)
    source_summary = service.source_summary_lines()
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
