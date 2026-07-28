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
from src.cli.run_mode import CliOptions, RunMode
from src.collectors.lhu_collector import LhuCollector
from src.collectors.structured_announcement_detail_fetcher import (
    StructuredAnnouncementDetailFetcher,
)
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.evaluators.structured_eligibility_evaluator import StructuredEligibilityEvaluator
from src.formatters.cli_output_formatter import print_audit_result, print_service_result
from src.notifiers.line_notifier import send_text_message
from src.notifiers.noop_notifier import discard_notification
from src.profiles.student_profile import load_student_profile
from src.repositories.gemini_cache_repository import GeminiCacheRepository
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.baseline_service import BaselineService
from src.services.gemini_fallback_service import (
    GeminiFallbackService,
    GeminiUsageLimiter,
)
from src.services.gemini_text_analysis_service import GeminiTextAnalysisService
from src.services.scholarship_service import AuditResult, ScholarshipService, ServiceResult

NotificationSender = Callable[[str], None]


def configure_console_output() -> None:
    """讓 Windows CP950 終端遇到特殊符號時替換字元而不中斷。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="replace")


def parse_args(argv: list[str] | None = None) -> CliOptions:
    """解析互斥 CLI 模式並轉成明確的 RunMode。"""
    parser = argparse.ArgumentParser(description="Scholarship Agent")
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
    namespace = parser.parse_args(argv)
    if namespace.initialize_baseline and namespace.use_gemini:
        parser.error("建立歷史基準時不需要 Gemini")

    if namespace.initialize_baseline:
        mode = RunMode.INITIALIZE_BASELINE
    elif namespace.audit:
        mode = RunMode.AUDIT
    elif namespace.dry_run:
        mode = RunMode.DRY_RUN
    else:
        mode = RunMode.LIVE
    return CliOptions(mode=mode, use_gemini=bool(namespace.use_gemini))


def build_live_notifier() -> NotificationSender:
    """建立可實際傳送 LINE 的正式 notifier。"""

    def _notify(text: str) -> None:
        send_text_message(
            api_url=LINE_API_URL,
            channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
            user_id=LINE_USER_ID,
            text=text,
            timeout_seconds=HTTP_TIMEOUT_SECONDS,
        )

    return _notify


def build_notifier(mode: RunMode) -> NotificationSender:
    """只有 live 模式可取得正式 notifier，其餘模式明確使用 no-op。"""
    return build_live_notifier() if mode is RunMode.LIVE else discard_notification


def _build_collector() -> LhuCollector:
    return LhuCollector(
        LHU_SCHOLARSHIP_URL,
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
    )


def _build_repository() -> ScholarshipRepository:
    return ScholarshipRepository(DATA_DIR / SCHOLARSHIP_DB_FILENAME)


def build_full_service(
    mode: RunMode,
    *,
    use_gemini: bool = False,
) -> ScholarshipService:
    """建立具備 profile、正文解析與資格判斷的完整服務。"""
    if mode is RunMode.INITIALIZE_BASELINE:
        raise ValueError("建立歷史基準必須使用 build_baseline_service")

    profile = load_student_profile(PROFILE_PATH)
    gemini_fallback, gemini_text_analysis = _build_gemini_services(use_gemini)
    return ScholarshipService(
        _build_collector(),
        _build_repository(),
        build_notifier(mode),
        include_keywords=SCHOLARSHIP_FILTER_KEYWORDS,
        summary_batch_size=LINE_SUMMARY_BATCH_SIZE,
        detail_fetcher=_build_detail_fetcher(),
        evaluator=EligibilityEvaluator(),
        profile=profile,
        notify_review_items=NOTIFY_REVIEW_ITEMS,
        gemini_fallback=gemini_fallback,
        gemini_text_analysis=gemini_text_analysis,
        structured_evaluator=(StructuredEligibilityEvaluator() if use_gemini else None),
    )


def build_baseline_service() -> BaselineService:
    """建立不載入 profile、Gemini 或 LINE 的基準服務。"""
    return BaselineService(
        _build_collector(),
        _build_repository(),
        include_keywords=SCHOLARSHIP_FILTER_KEYWORDS,
    )


def _build_detail_fetcher() -> StructuredAnnouncementDetailFetcher:
    return StructuredAnnouncementDetailFetcher(
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
    """保留既有測試與內部呼叫介面。"""
    fallback, _ = _build_gemini_services(use_gemini)
    return fallback


def execute_full_service(
    options: CliOptions,
    service: ScholarshipService,
) -> ServiceResult | AuditResult:
    """依明確 RunMode 執行完整服務，不使用負條件推測模式。"""
    if options.mode is RunMode.LIVE:
        return service.run(dry_run=False)
    if options.mode is RunMode.DRY_RUN:
        return service.run(dry_run=True)
    if options.mode is RunMode.AUDIT:
        return service.audit()
    raise ValueError("baseline 模式不能交給完整服務執行")


def main(argv: list[str] | None = None) -> None:
    configure_console_output()
    options = parse_args(argv)

    if options.mode is RunMode.LIVE:
        validate_settings()
    if options.use_gemini:
        validate_gemini_settings()

    if options.mode is RunMode.INITIALIZE_BASELINE:
        result = build_baseline_service().initialize_baseline()
        print_service_result(result)
        return

    service = build_full_service(options.mode, use_gemini=options.use_gemini)
    result = execute_full_service(options, service)
    if isinstance(result, AuditResult):
        print_audit_result(result)
        csv_path, json_path = write_structured_shadow_artifacts(result)
        print(f"Structured CSV：{csv_path}")
        print(f"Structured JSON：{json_path}")
        return
    print_service_result(result)


if __name__ == "__main__":
    main()
