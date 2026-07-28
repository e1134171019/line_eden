# -*- coding: utf-8 -*-

from typing import Protocol

from src.formatters.audit_diagnostic_formatter import build_fetch_diagnostic_lines
from src.models.scholarship import Scholarship
from src.services.gemini_fallback_service import GeminiAnalysisDiagnostic
from src.services.scholarship_service import AuditRecord, AuditResult, ServiceResult


class GeminiUsageView(Protocol):
    """可供主控台顯示 Gemini 用量的結構介面。"""

    gemini_calls: int
    gemini_cache_hits: int
    gemini_input_tokens: int
    gemini_output_tokens: int


def print_summary(result: ServiceResult) -> None:
    print(f"蒐集公告數量：{len(result.collected)}")
    print(f"適合且待通知：{len(result.pending_items)}")
    print(f"明確適合：{result.eligible_count}")
    print(f"資格待確認：{result.review_count}")
    print(f"明確不符合：{result.ineligible_count}")
    print(f"本次通知數量：{result.notified_count}")
    print(f"本次基準化數量：{result.baseline_count}")
    print_gemini_usage(result)


def print_items(label: str, items: list[Scholarship]) -> None:
    print(label)
    if not items:
        print("- 無")
        return
    for item in items:
        print(f"- {item.published_date} | {item.title} | {item.eligibility_reason}")
        print(f"  {item.source_url}")


def print_audit(result: AuditResult) -> None:
    print(f"稽核公告數量：{len(result.records)}")
    print(f"明確適合：{result.eligible_count}")
    print(f"資格待確認：{result.review_count}")
    print(f"不推播：{result.ineligible_count}")
    print(f"Structured 已比較：{result.structured_evaluated_count}")
    print(f"Structured 分歧：{result.structured_changed_count}")
    print(f"Structured 預算延後：{result.structured_deferred_count}")
    print(f"Structured 錯誤：{result.structured_error_count}")
    print_gemini_usage(result)
    for record in result.records:
        print_audit_record(record)
    print(result.message)


def print_audit_record(record: AuditRecord) -> None:
    item = record.item
    print(f"- {item.published_date} | {item.notice_kind} | {item.eligibility_status}")
    print(f"  {item.title} | {item.eligibility_reason}")
    print(f"  正文摘要：{record.detail_excerpt or '無法擷取'}")
    for line in build_fetch_diagnostic_lines(record.fetch_result):
        print(line)
    if record.gemini_diagnostic:
        print_gemini_diagnostic(record.gemini_diagnostic)
    print(f"  Shadow狀態：{record.shadow_status}")
    if record.structured_gemini_diagnostic:
        print_gemini_diagnostic(record.structured_gemini_diagnostic)
    if record.structured_shadow:
        shadow = record.structured_shadow
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
    print(f"  {item.source_url}")


def print_gemini_diagnostic(diagnostic: GeminiAnalysisDiagnostic) -> None:
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


def print_gemini_usage(result: GeminiUsageView) -> None:
    print(f"Gemini 生成呼叫：{result.gemini_calls}")
    print(f"Gemini 快取命中：{result.gemini_cache_hits}")
    print(f"Gemini input tokens：{result.gemini_input_tokens}")
    print(f"Gemini output tokens：{result.gemini_output_tokens}")
