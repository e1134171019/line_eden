# -*- coding: utf-8 -*-

import argparse
import sys
from typing import Callable

from config import (
    DATA_DIR,
    GEMINI_API_KEY,
    GEMINI_CACHE_DB_FILENAME,
    GEMINI_MAX_CALLS_PER_RUN,
    GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT,
    GEMINI_MAX_INPUT_TOKENS_PER_RUN,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_MAX_PAGES_PER_DOCUMENT,
    GEMINI_MODEL,
    GEMINI_PROMPT_VERSION,
    HTTP_TIMEOUT_SECONDS,
    HTTP_USER_AGENT,
    LHU_SCHOLARSHIP_URL,
    LINE_API_URL,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_SUMMARY_BATCH_SIZE,
    LINE_USER_ID,
    MAX_ATTACHMENT_COUNT,
    MAX_DOWNLOAD_BYTES,
    MAX_PDF_PAGES,
    NOTIFY_REVIEW_ITEMS,
    PROFILE_PATH,
    SCHOLARSHIP_DB_FILENAME,
    SCHOLARSHIP_FILTER_KEYWORDS,
    validate_gemini_settings,
    validate_settings,
)
from src.ai.gemini_requirement_extractor import GeminiRequirementExtractor
from src.ai.gemini_text_requirement_extractor import GeminiTextRequirementExtractor
from src.automation.structured_shadow_artifact import write_structured_shadow_artifacts
from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.collectors.lhu_collector import LhuCollector
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.evaluators.structured_eligibility_evaluator import StructuredEligibilityEvaluator
from src.formatters.audit_diagnostic_formatter import build_fetch_diagnostic_lines
from src.models.scholarship import Scholarship
from src.notifiers.line_notifier import send_text_message
from src.profiles.student_profile import load_student_profile
from src.repositories.gemini_cache_repository import GeminiCacheRepository
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.gemini_fallback_service import (
    GeminiAnalysisDiagnostic,
    GeminiFallbackService,
    GeminiUsageLimiter,
)
from src.services.gemini_text_analysis_service import GeminiTextAnalysisService
from src.services.scholarship_service import (
    AuditRecord,
    AuditResult,
    ScholarshipService,
    ServiceResult,
)


def configure_console_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scholarship Agent 第三階段")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="評估適合度但不傳 LINE")
    modes.add_argument("--audit", action="store_true", help="重新稽核全部公告但不改獎學金狀態")
    modes.add_argument(
        "--initialize-baseline",
        action="store_true",
        help="將目前公告設為歷史基準，不傳 LINE",
    )
    parser.add_argument(
        "--use-gemini",
        action="store_true",
        help="啟用掃描 PDF 備援；audit 另執行文字 structured shadow",
    )
    args = parser.parse_args(argv)
    if args.initialize_baseline and args.use_gemini:
        parser.error("建立歷史基準時不需要 Gemini")
    return args


def build_notifier() -> Callable[[str], None]:
    def _notify(text: str) -> None:
        send_text_message(
            api_url=LINE_API_URL,
            channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
            user_id=LINE_USER_ID,
            text=text,
            timeout_seconds=HTTP_TIMEOUT_SECONDS,
        )

    return _notify


def build_service(
    profile_required: bool = True,
    use_gemini: bool = False,
) -> ScholarshipService:
    collector = LhuCollector(
        LHU_SCHOLARSHIP_URL,
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
    )
    repository = ScholarshipRepository(DATA_DIR / SCHOLARSHIP_DB_FILENAME)
    profile = load_student_profile(PROFILE_PATH) if profile_required else None
    gemini_fallback, gemini_text_analysis = _build_gemini_services(use_gemini)
    return ScholarshipService(
        collector,
        repository,
        build_notifier(),
        include_keywords=SCHOLARSHIP_FILTER_KEYWORDS,
        summary_batch_size=LINE_SUMMARY_BATCH_SIZE,
        detail_fetcher=_build_detail_fetcher(profile_required),
        evaluator=EligibilityEvaluator() if profile_required else None,
        profile=profile,
        notify_review_items=NOTIFY_REVIEW_ITEMS,
        gemini_fallback=gemini_fallback,
        gemini_text_analysis=gemini_text_analysis,
        structured_evaluator=(
            StructuredEligibilityEvaluator()
            if profile_required and use_gemini
            else None
        ),
    )


def _build_detail_fetcher(
    profile_required: bool,
) -> AnnouncementDetailFetcher | None:
    if not profile_required:
        return None
    return AnnouncementDetailFetcher(
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
        MAX_ATTACHMENT_COUNT,
        MAX_DOWNLOAD_BYTES,
        MAX_PDF_PAGES,
    )


def _build_gemini_services(
    use_gemini: bool,
) -> tuple[GeminiFallbackService | None, GeminiTextAnalysisService | None]:
    if not use_gemini:
        return None, None
    extractor = GeminiRequirementExtractor(
        GEMINI_API_KEY,
        GEMINI_MODEL,
        GEMINI_MAX_PAGES_PER_DOCUMENT,
        MAX_DOWNLOAD_BYTES,
        GEMINI_MAX_INPUT_TOKENS_PER_DOCUMENT,
        GEMINI_MAX_OUTPUT_TOKENS,
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
    )
    cache = GeminiCacheRepository(DATA_DIR / GEMINI_CACHE_DB_FILENAME)
    limiter = GeminiUsageLimiter(
        GEMINI_MAX_CALLS_PER_RUN,
        GEMINI_MAX_INPUT_TOKENS_PER_RUN,
    )
    fallback = GeminiFallbackService(extractor, cache, limiter, GEMINI_PROMPT_VERSION)
    text_service = GeminiTextAnalysisService(
        GeminiTextRequirementExtractor(extractor),
        cache,
        limiter,
        f"{GEMINI_PROMPT_VERSION}-text-v1",
    )
    return fallback, text_service


def _build_gemini_fallback(use_gemini: bool) -> GeminiFallbackService | None:
    """保留既有測試與呼叫介面。"""
    fallback, _ = _build_gemini_services(use_gemini)
    return fallback


def execute_service(
    args: argparse.Namespace,
    service: ScholarshipService,
) -> ServiceResult | AuditResult:
    if args.initialize_baseline:
        return service.initialize_baseline()
    if args.audit:
        return service.audit()
    return service.run(dry_run=args.dry_run)


def print_summary(result: ServiceResult) -> None:
    print(f"蒐集公告數量：{len(result.collected)}")
    print(f"適合且待通知：{len(result.pending_items)}")
    print(f"明確適合：{result.eligible_count}")
    print(f"資格待確認：{result.review_count}")
    print(f"明確不符合：{result.ineligible_count}")
    print(f"本次通知數量：{result.notified_count}")
    print(f"本次基準化數量：{result.baseline_count}")
    _print_gemini_usage(result)


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
    _print_gemini_usage(result)
    for record in result.records:
        _print_audit_record(record)
    print(result.message)


def _print_audit_record(record: AuditRecord) -> None:
    item = record.item
    print(f"- {item.published_date} | {item.notice_kind} | {item.eligibility_status}")
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


def _print_gemini_usage(result: object) -> None:
    print(f"Gemini 生成呼叫：{result.gemini_calls}")
    print(f"Gemini 快取命中：{result.gemini_cache_hits}")
    print(f"Gemini input tokens：{result.gemini_input_tokens}")
    print(f"Gemini output tokens：{result.gemini_output_tokens}")


def _is_live_mode(args: argparse.Namespace) -> bool:
    return not args.dry_run and not args.audit and not args.initialize_baseline


def main(argv: list[str] | None = None) -> None:
    configure_console_output()
    args = parse_args(argv)
    if _is_live_mode(args):
        validate_settings()
    if args.use_gemini:
        validate_gemini_settings()
    service = build_service(
        profile_required=not args.initialize_baseline,
        use_gemini=args.use_gemini,
    )
    result = execute_service(args, service)
    if isinstance(result, AuditResult):
        print_audit(result)
        csv_path, json_path = write_structured_shadow_artifacts(result)
        print(f"Structured CSV：{csv_path}")
        print(f"Structured JSON：{json_path}")
        return
    print_summary(result)
    print_items("適合且待通知公告：", result.pending_items)
    print(result.message)


if __name__ == "__main__":
    main()
