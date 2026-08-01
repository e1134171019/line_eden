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
from src.evaluators.runtime_safety import (
    EXPIRED,
    STALE_UNKNOWN,
    classify_application_period,
)
from src.notifiers.line_notifier import send_text_message
from src.runtime.run_mode import RunMode
from src.services.scholarship_service import AuditRecord, AuditResult

MAX_LINE_TEXT_LENGTH = 4800
MAX_ELIGIBLE_ITEMS = 5
MAX_REVIEW_ITEMS = 5
MAX_SHADOW_CHANGED_ITEMS = 10
MAX_SHADOW_ERROR_ITEMS = 8
MAX_SOURCE_ERROR_ITEMS = 8
MAX_MANUAL_CHECKS_PER_ITEM = 3
MAX_DETAIL_TITLE_LENGTH = 34
MAX_DETAIL_REASON_LENGTH = 82

_REVIEW_LABELS = {
    "source_incomplete": "來源不完整",
    "profile_missing": "個人資料缺值",
    "semantic_ambiguous": "語意待確認",
}
_NON_ACTIONABLE_PERIODS = {EXPIRED, STALE_UNKNOWN}


def build_report_message(
    result: AuditResult,
    source_lines: Sequence[str] = (),
) -> str:
    """建立可行動公告優先、來源狀態壓縮的 LINE 稽核報告。"""

    lines = [
        "獎學金真實檢查報告",
        f"本次稽核公告：{len(result.records)}",
        *_scope_lines(result.records),
        *_pipeline_lines(result),
        f"Gemini 生成呼叫：{result.gemini_calls}",
        f"Gemini 快取命中：{result.gemini_cache_hits}",
        "",
        *_actionable_lines(result),
        "",
        "Structured shadow：",
        f"- 已比較：{result.structured_evaluated_count}",
        f"- 與 legacy 分歧：{result.structured_changed_count}",
        f"- 預算延後：{result.structured_deferred_count}",
        f"- 抽取錯誤：{result.structured_error_count}",
        *_structured_detail_lines(result.records),
    ]
    if source_lines:
        lines.extend(["", "來源狀態：", *_compact_source_lines(source_lines)])
    return "\n".join(lines)[:MAX_LINE_TEXT_LENGTH]


def _pipeline_lines(result: AuditResult) -> list[str]:
    counts = getattr(result, "pipeline_counts", None)
    if counts is None:
        return []
    return [
        (
            "管線："
            f"原始 {counts.raw_collected}／"
            f"保留 {counts.relevance_accepted}／"
            f"排除 {counts.relevance_excluded}／"
            f"申請型 {counts.application}／"
            f"非申請型 {counts.non_application}／"
            f"可通知 {counts.notifiable}"
        )
    ]


def _scope_lines(records: list[AuditRecord]) -> list[str]:
    """建立公告分類、申請期間、正文證據與硬性資格統計。"""

    notice_counts = Counter(record.item.notice_kind for record in records)
    category_counts = Counter(record.item.category for record in records)
    applications = [
        record for record in records if record.item.notice_kind == APPLICATION
    ]
    periods = {id(record): _period_status(record) for record in applications}
    period_counts = Counter(periods[id(record)] for record in applications)
    actionable = [
        record
        for record in applications
        if periods[id(record)] not in _NON_ACTIONABLE_PERIODS
    ]
    eligibility_counts = Counter(
        record.item.eligibility_status for record in actionable
    )
    review_counts = Counter(
        record.item.review_kind
        for record in actionable
        if record.item.eligibility_status == REVIEW and record.item.review_kind
    )
    evidence_counts = Counter(
        record.item.resolution_status or "unknown" for record in applications
    )
    non_application = len(records) - notice_counts[APPLICATION]
    lines = [
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
            f"常年 {period_counts['evergreen']}／"
            f"已截止 {period_counts['expired']}／"
            f"近期未知 {period_counts['deadline_unknown']}／"
            f"歷史未知 {period_counts['stale_unknown']}"
        ),
        (
            "正文證據："
            f"完整 {evidence_counts['valid_application_detail']}／"
            f"不足 {evidence_counts['insufficient_evidence']}／"
            f"錯頁 {evidence_counts['navigation_or_wrong_page']}／"
            f"來源錯誤 {evidence_counts['source_error']}"
        ),
        (
            "硬性資格（可行動期間）："
            f"符合 {eligibility_counts[ELIGIBLE]}／"
            f"待確認 {eligibility_counts[REVIEW]}／"
            f"不符 {eligibility_counts[INELIGIBLE]}"
        ),
        f"已截止未列為個人資格不符：{period_counts['expired']}",
        f"歷史期限未知未列入可申請：{period_counts['stale_unknown']}",
        f"非申請公告未列入個人資格：{non_application}",
    ]
    if review_counts:
        lines.append(
            "待確認原因："
            + "／".join(
                f"{_REVIEW_LABELS.get(kind, kind)} {count}"
                for kind, count in sorted(review_counts.items())
            )
        )
    return lines


def _actionable_lines(result: AuditResult) -> list[str]:
    eligible = _records_with_status(result.records, ELIGIBLE)
    review = _records_with_status(result.records, REVIEW)
    if not eligible and not review:
        return ["目前沒有硬性條件符合或待確認且仍可申請的公告。"]
    lines: list[str] = []
    if eligible:
        lines.append("硬性條件符合公告：")
        lines.extend(_item_lines(record) for record in eligible[:MAX_ELIGIBLE_ITEMS])
        remaining = len(eligible) - MAX_ELIGIBLE_ITEMS
        if remaining > 0:
            lines.append(f"另有 {remaining} 筆硬性條件符合公告未列出。")
    if review:
        lines.append("硬性條件待確認公告：")
        lines.extend(_item_lines(record) for record in review[:MAX_REVIEW_ITEMS])
        remaining = len(review) - MAX_REVIEW_ITEMS
        if remaining > 0:
            lines.append(f"另有 {remaining} 筆待確認公告未列出。")
    return lines


def _records_with_status(
    records: list[AuditRecord],
    status: str,
) -> list[AuditRecord]:
    return [
        record
        for record in records
        if record.item.notice_kind == APPLICATION
        and record.item.eligibility_status == status
        and _period_status(record) not in _NON_ACTIONABLE_PERIODS
    ]


def _item_lines(record: AuditRecord) -> str:
    item = record.item
    title = _short(item.title, MAX_DETAIL_TITLE_LENGTH)
    reason = _short(item.eligibility_reason, MAX_DETAIL_REASON_LENGTH)
    url = item.detail_url or item.source_url
    published = item.published_date or "日期未知"
    lines = [f"- {published}｜{title}", f"  {reason}"]
    if item.review_kind:
        lines.append(f"  類型：{_REVIEW_LABELS.get(item.review_kind, item.review_kind)}")
    if item.manual_checks:
        checks = [
            _short(_strip_manual_prefix(value), MAX_DETAIL_REASON_LENGTH)
            for value in item.manual_checks[:MAX_MANUAL_CHECKS_PER_ITEM]
        ]
        lines.append("  自行確認：" + "；".join(checks))
    lines.append(
        f"  正文證據：{item.detail_evidence_score}｜{item.resolution_status or 'unknown'}"
    )
    lines.append(f"  {url}")
    return "\n".join(lines)


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
    shadow = record.structured_shadow
    return bool(shadow and shadow.changed)


def _is_shadow_error(record: AuditRecord) -> bool:
    return record.shadow_status in {"text_error", "text_cached_error"}


def _changed_line(record: AuditRecord) -> str:
    shadow = record.structured_shadow
    assert shadow is not None
    title = _short(record.item.title, MAX_DETAIL_TITLE_LENGTH)
    reason = _short(shadow.structured_reason, MAX_DETAIL_REASON_LENGTH)
    return f"- {title}：{shadow.legacy_status}→{shadow.structured_status}；{reason}"


def _error_line(record: AuditRecord) -> str:
    diagnostic = record.structured_gemini_diagnostic
    title = _short(record.item.title, MAX_DETAIL_TITLE_LENGTH)
    message = diagnostic.message if diagnostic else "未提供錯誤診斷"
    return f"- {title}：{_short(message, MAX_DETAIL_REASON_LENGTH)}"


def _short(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


def _strip_manual_prefix(value: str) -> str:
    prefix = "請自行確認："
    return value[len(prefix):].strip() if value.startswith(prefix) else value


def _compact_source_lines(source_lines: Sequence[str]) -> list[str]:
    regular = [line for line in source_lines if not line.startswith("TUN方案 ")]
    tun_lines = [line for line in source_lines if line.startswith("TUN方案 ")]
    if not tun_lines:
        return [f"- {line}" for line in regular]
    statuses = Counter(_tun_status(line) for line in tun_lines)
    status_text = "／".join(
        f"{status} {count}" for status, count in sorted(statuses.items())
    )
    abnormal = [
        line
        for line in tun_lines
        if _tun_status(line) in {"fetch_failed", "pending_source"}
    ]
    lines = [*(f"- {line}" for line in regular)]
    lines.append(f"- TUN方案共 {len(tun_lines)}：{status_text}")
    lines.extend(f"- {line}" for line in abnormal[:MAX_SOURCE_ERROR_ITEMS])
    remaining = len(abnormal) - MAX_SOURCE_ERROR_ITEMS
    if remaining > 0:
        lines.append(f"- 另有 {remaining} 項 TUN 異常狀態未列出。")
    return lines


def _tun_status(line: str) -> str:
    if "：" not in line:
        return "unknown"
    return line.split("：", 1)[1].split("；", 1)[0].strip() or "unknown"


def _period_status(record: AuditRecord) -> str:
    saved = record.item.application_status
    if saved and saved != "not_applicable":
        return saved
    text = record.fetch_result.eligibility_text()
    return classify_application_period(text, record.item.published_date).status


def main() -> None:
    """重新稽核七個 collector 群組並傳送 LINE，不修改通知狀態。"""

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
