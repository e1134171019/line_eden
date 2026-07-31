# -*- coding: utf-8 -*-

import argparse
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
    SOURCE_FETCH_WORKERS,
    SOURCE_MAX_PAGES,
    validate_gemini_settings,
    validate_settings,
)
from src.ai.gemini_requirement_extractor import GeminiRequirementExtractor
from src.ai.gemini_text_requirement_extractor import GeminiTextRequirementExtractor
from src.automation.structured_shadow_artifact import write_structured_shadow_artifacts
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.evidence_detail_fetcher import EvidenceDetailFetcher
from src.collectors.expanded_scholarship_collector import ExpandedScholarshipCollector
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.evaluators.structured_eligibility_evaluator import StructuredEligibilityEvaluator
from src.formatters.cli_output_formatter import (
    configure_console_output,
    print_audit,
    print_items,
    print_summary,
)
from src.notifiers.line_notifier import send_text_message
from src.profiles.student_profile import load_student_profile
from src.repositories.gemini_cache_repository import GeminiCacheRepository
from src.repositories.scholarship_repository import ScholarshipRepository
from src.runtime.run_mode import RunMode
from src.services.baseline_service import BaselineService
from src.services.gemini_fallback_service import (
    GeminiFallbackService,
    GeminiUsageLimiter,
)
from src.services.gemini_text_analysis_service import GeminiTextAnalysisService
from src.services.scholarship_service import AuditResult, ScholarshipService, ServiceResult

Notifier = Callable[[str], None]


class ParsedArgs(argparse.Namespace):
    """Scholarship Agent 已知的命令列欄位。"""

    dry_run: bool
    audit: bool
    initialize_baseline: bool
    use_gemini: bool


def parse_args(argv: list[str] | None = None) -> ParsedArgs:
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
    args = ParsedArgs()
    parser.parse_args(argv, namespace=args)
    if args.initialize_baseline and args.use_gemini:
        parser.error("建立歷史基準時不需要 Gemini")
    return args


def resolve_run_mode(args: ParsedArgs) -> RunMode:
    """將命令列旗標解析成單一明確模式。"""
    if args.initialize_baseline:
        return RunMode.INITIALIZE_BASELINE
    if args.audit:
        return RunMode.AUDIT
    if args.dry_run:
        return RunMode.DRY_RUN
    return RunMode.LIVE


def _discard_notification(_: str) -> None:
    """非正式模式的通知接收器，明確丟棄訊息。"""


def build_notifier(mode: RunMode) -> Notifier:
    """只有 LIVE／DAILY 模式能取得真正的 LINE notifier。"""
    if not mode.sends_scholarship_notifications:
        return _discard_notification

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
    *,
    mode: RunMode = RunMode.LIVE,
    use_gemini: bool = False,
) -> ScholarshipService:
    """建立具備學生背景、正文擷取與資格判斷的完整服務。"""
    if not mode.requires_profile:
        raise ValueError("基準模式必須使用 build_baseline_service()")

    profile = load_student_profile(PROFILE_PATH)
    gemini_fallback, gemini_text_analysis = _build_gemini_services(use_gemini)
    return ScholarshipService(
        _build_collector(mode),
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
    """建立不含 profile、evaluator、Gemini 與 notifier 的基準服務。"""
    return BaselineService(
        _build_collector(RunMode.INITIALIZE_BASELINE),
        _build_repository(),
        SCHOLARSHIP_FILTER_KEYWORDS,
    )


# 稽核與基準抓完整分頁；每日、正式與 dry-run 僅抓最新入口頁。
def _collection_mode(mode: RunMode) -> CollectionMode:
    if mode in {RunMode.AUDIT, RunMode.INITIALIZE_BASELINE}:
        return CollectionMode.FULL_AUDIT
    return CollectionMode.INCREMENTAL


# 建立六個既有來源與 38 項方案官方監測群組。
def _build_collector(mode: RunMode) -> ExpandedScholarshipCollector:
    return ExpandedScholarshipCollector(
        LHU_SCHOLARSHIP_URL,
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
        _collection_mode(mode),
        SOURCE_MAX_PAGES,
        SOURCE_FETCH_WORKERS,
    )


def _build_repository() -> ScholarshipRepository:
    return ScholarshipRepository(DATA_DIR / SCHOLARSHIP_DB_FILENAME)


def _build_detail_fetcher() -> EvidenceDetailFetcher:
    return EvidenceDetailFetcher(
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


def execute_service(
    mode: RunMode,
    service: ScholarshipService,
) -> ServiceResult | AuditResult:
    """執行需要完整學生背景的模式；baseline 不得進入此函式。"""
    if mode is RunMode.AUDIT:
        return service.audit()
    if mode is RunMode.DRY_RUN:
        return service.run(dry_run=True)
    if mode in {RunMode.LIVE, RunMode.DAILY}:
        return service.run(dry_run=False)
    raise ValueError("基準模式必須由 BaselineService 執行")


def main(argv: list[str] | None = None) -> None:
    configure_console_output()
    args = parse_args(argv)
    mode = resolve_run_mode(args)

    if mode.validates_line_settings:
        validate_settings()
    if args.use_gemini:
        validate_gemini_settings()

    if mode is RunMode.INITIALIZE_BASELINE:
        result: ServiceResult | AuditResult = build_baseline_service().initialize_baseline()
    else:
        result = execute_service(
            mode,
            build_service(mode=mode, use_gemini=args.use_gemini),
        )

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
