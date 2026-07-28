# -*- coding: utf-8 -*-

from collections import Counter
import sys

from src.evaluators.notice_classifier import APPLICATION
from src.evaluators.runtime_safety import NOT_APPLICABLE, classify_application_period
from src.formatters.audit_diagnostic_formatter import build_fetch_diagnostic_lines
from src.models.scholarship import Scholarship
from src.services.gemini_fallback_service import GeminiAnalysisDiagnostic
from src.services.scholarship_service import AuditRecord, AuditResult, ServiceResult

GeminiUsageResult = ServiceResult | AuditResult


# 讓 Windows CP950 終端遇到特殊符號時不中斷。
def configure_console_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="replace")


# 顯示一般執行摘要。
def print_summary(result: ServiceResult) -> None:
    print(f"蒐集公告數量：{len(result.collected)}")
    print(f"適合且待通知：{len(result.pending_items)}")
    print(f"明確適合：{result.eligible_count}")
    print(f"資格待確認：{result.review_count}")
    print(f"明確不符合：{result.ineligible_count}")
    print(f"本次通知數量：{result.notified_count}")
    print(f"本次基準化數量：{result.baseline_count}")
    _print_gemini_usage(result)


# 顯示公告清單。
def print_items(label: str, items: list[Scholarship]) -> None:
    print(label)
    if not items:
        print("- 無")
        return
    for item in items:
        print(f"- {item.published_date} | {item.title} | {item.eligibility_reason}")
        print(f"  {item.source_url}")


# 顯示稽核總覽與逐筆證據。
def print_audit(result: AuditResult) -> None:
    print(f"稽核原始公告：{len(result.records)}")
    _print_audit_scope_summary(result.records)
    print(f"明確適合：{result.eligible_count}")
    print(f"資格待確認：{result.review_count}")
    print(f"不推播：{result.ineligible_count}")
    print(f"Structured 已比較：{result.structured_evaluated_count}")
    print(f"Structured 分歧：{result.structured_changed_count}")
    print(f"Structured 預算延後：{result.structured_deferred_count}")
    print(f"Structured 錯誤：{result.structured_error_count}")
    _print_gemini_usage(result)
    for record in result.records:
        _print_audit_record(record)
    print(result.message)


# 分開顯示公告性質、獎助類別與申請期間狀態。
def _print_audit_scope_summary(records: list[AuditRecord]) -> None:
    notice_counts = Counter(record.item.notice_kind for record in records)
    category_counts = Counter(record.item.category for record in records)
    period_counts = Counter(
        _period_status(record)
        for record in records
        if record.item.notice_kind == APPLICATION
    )
    print(f"申請型公告：{notice_counts[APPLICATION]}")
    print(f"非申請型公告：{len(records) - notice_counts[APPLICATION]}")
    print(
        "公告類別："
        f"獎學金 {category_counts['scholarship']}、"
        f"助學金 {category_counts['student_aid']}、"
        f"補助 {category_counts['subsidy']}、"
        f"就學貸款 {category_counts['loan']}、"
        f"其他 {category_counts['other']}"
    )
    print(
        "申請狀態："
        f"開放 {period_counts['open']}、"
        f"尚未開始 {period_counts['upcoming']}、"
        f"已截止 {period_counts['expired']}、"
        f"期限未知 {period_counts['deadline_unknown']}"
    )


# 顯示單筆稽核結果。
def _print_audit_record(record: AuditRecord) -> None:
    item = record.item
    period_status = _period_status(record)
    print(
        f"- {item.published_date} | {item.notice_kind} | {item.category} | "
        f"{period_status} | {item.eligibility_status}"
    )
    print(f"  {item.title} | {item.eligibility_reason}")
    print(f"  正文摘要：{record.detail_excerpt or '無法擷取'}")
    for line in build_fetch_diagnostic_lines(record.fetch_result):
        print(line)
    if record.gemini_diagnostic:
        _print_gemini_diagnostic(record.gemini_diagnostic)
    print(f"  Shadow狀態：{record.shadow_status}")
    if record.structured_gemini_diagnostic:
        _print_gemini_diagnostic(record.structured_gemini_diagnostic)
    if record.structured_shadow:
        _print_structured_shadow(record)
    print(f"  {item.source_url}")


# 顯示 structured shadow 條件矩陣。
def _print_structured_shadow(record: AuditRecord) -> None:
    shadow = record.structured_shadow
    assert shadow is not None
    print(
        "  Shadow比較："
        f"legacy={shadow.legacy_status} | structured={shadow.structured_status} | "
        f"changed={shadow.changed}"
    )
    print(f"  Structured理由：{shadow.structured_reason}")
    for condition in shadow.conditions:
        print(
            "  Structured條件："
            f"{condition.status} | {condition.field} | "
            f"{condition.requirement} | {condition.reason}"
        )


# 依公告正文推導申請期間狀態；非申請公告不套用期間判斷。
def _period_status(record: AuditRecord) -> str:
    if record.item.notice_kind != APPLICATION:
        return NOT_APPLICABLE
    text = record.fetch_result.eligibility_text()
    return classify_application_period(text, record.item.published_date).status


# 顯示單次 Gemini 診斷。
def _print_gemini_diagnostic(diagnostic: GeminiAnalysisDiagnostic) -> None:
    cache = "是" if diagnostic.cache_hit else "否"
    print(
        "  Gemini診斷："
        f"{diagnostic.status} | {diagnostic.model} | 快取 {cache} | "
        f"頁數 {diagnostic.selected_pages} | input {diagnostic.input_tokens} | "
        f"output {diagnostic.output_tokens}"
    )
    print(f"  Gemini說明：{diagnostic.message}")
    for field in diagnostic.extracted_fields:
        print(f"  Gemini欄位：{field}")
    for evidence in diagnostic.evidence:
        print(f"  Gemini證據：{evidence}")
    print(f"  Gemini來源：{diagnostic.source_url}")


# 顯示 Gemini 使用量。
def _print_gemini_usage(result: GeminiUsageResult) -> None:
    print(f"Gemini 生成呼叫：{result.gemini_calls}")
    print(f"Gemini 快取命中：{result.gemini_cache_hits}")
    print(f"Gemini input tokens：{result.gemini_input_tokens}")
    print(f"Gemini output tokens：{result.gemini_output_tokens}")
