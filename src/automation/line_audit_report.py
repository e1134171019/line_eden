# -*- coding: utf-8 -*-

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
from src.evaluators.runtime_safety import EXPIRED, STALE_UNKNOWN, classify_application_period
from src.notifiers.line_notifier import send_text_message
from src.runtime.run_mode import RunMode
from src.services.scholarship_service import AuditRecord, AuditResult

MAX_LINE_TEXT_LENGTH = 4800
_NON_ACTIONABLE_PERIODS = {EXPIRED, STALE_UNKNOWN, "not_applicable"}


def build_report_message(
    result: AuditResult,
    source_lines: Sequence[str] = (),
) -> str:
    """LINE 稽核報告只列硬性資格符合且仍可申請的公告連結。"""

    # 來源狀態仍保留在內部診斷與 artifact，不進入 LINE 訊息。
    _ = source_lines
    records = _eligible_records(result.records)
    if not records:
        return "目前沒有符合資格且仍可申請的獎學金。"

    lines = ["【符合資格獎學金】"]
    seen_urls: set[str] = set()
    visible_index = 0
    for record in records:
        item = record.item
        url = item.detail_url or item.source_url
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        visible_index += 1
        block = [f"{visible_index}. {item.title}", url]
        candidate = "\n".join([*lines, *block])
        if len(candidate) > MAX_LINE_TEXT_LENGTH:
            break
        lines.extend(block)
    return "\n".join(lines)


def _eligible_records(records: list[AuditRecord]) -> list[AuditRecord]:
    return [
        record
        for record in records
        if record.item.notice_kind == APPLICATION
        and _hard_status(record) == ELIGIBLE
        and _period_status(record) not in _NON_ACTIONABLE_PERIODS
    ]


def _hard_status(record: AuditRecord) -> str:
    saved = getattr(record.item, "hard_eligibility_status", "")
    return saved or record.item.eligibility_status


def _period_status(record: AuditRecord) -> str:
    saved = record.item.application_status
    if saved and saved != "not_applicable":
        return saved
    text = record.fetch_result.eligibility_text()
    return classify_application_period(text, record.item.published_date).status


def main() -> None:
    """完整稽核後，LINE 僅傳送符合資格的公告名稱與連結。"""

    validate_settings()
    validate_gemini_settings()
    service = build_service(mode=RunMode.AUDIT, use_gemini=True)
    result = service.audit()
    csv_path, json_path = write_structured_shadow_artifacts(result)
    message = build_report_message(result)
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
    print("符合資格連結已傳送至 LINE。")


if __name__ == "__main__":
    main()
