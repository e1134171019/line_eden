# -*- coding: utf-8 -*-

import argparse
import sys
from typing import Callable

from config import (
    DATA_DIR,
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
    validate_settings,
)
from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.collectors.lhu_collector import LhuCollector
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.formatters.audit_diagnostic_formatter import build_fetch_diagnostic_lines
from src.notifiers.line_notifier import send_text_message
from src.profiles.student_profile import load_student_profile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import (
    AuditRecord,
    AuditResult,
    ScholarshipService,
    ServiceResult,
)


# 讓 Windows CP950 終端遇到特殊符號時替換字元而不中斷。
def configure_console_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="replace")


# 解析命令列參數，並限制執行模式只能擇一。
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scholarship Agent 第三階段")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="評估適合度但不傳 LINE")
    modes.add_argument("--audit", action="store_true", help="重新稽核全部公告但不改資料庫")
    modes.add_argument(
        "--initialize-baseline",
        action="store_true",
        help="將目前公告設為歷史基準，不傳 LINE",
    )
    return parser.parse_args(argv)


# 建立正式模式通知函式，封裝既有 LINE 推播核心呼叫。
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


# 建立公告蒐集、資料庫、資格判斷與通知服務。
def build_service(profile_required: bool = True) -> ScholarshipService:
    collector = LhuCollector(
        LHU_SCHOLARSHIP_URL,
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
    )
    repository = ScholarshipRepository(DATA_DIR / SCHOLARSHIP_DB_FILENAME)
    profile = load_student_profile(PROFILE_PATH) if profile_required else None
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
    )


# 需要個人化判斷時建立正文、短網址與附件擷取器。
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


# 依命令列模式執行服務。
def execute_service(
    args: argparse.Namespace,
    service: ScholarshipService,
) -> ServiceResult | AuditResult:
    if args.initialize_baseline:
        return service.initialize_baseline()
    if args.audit:
        return service.audit()
    return service.run(dry_run=args.dry_run)


# 印出蒐集、適合度、通知與基準化摘要。
def print_summary(result: ServiceResult) -> None:
    print(f"蒐集公告數量：{len(result.collected)}")
    print(f"適合且待通知：{len(result.pending_items)}")
    print(f"明確適合：{result.eligible_count}")
    print(f"資格待確認：{result.review_count}")
    print(f"明確不符合：{result.ineligible_count}")
    print(f"本次通知數量：{result.notified_count}")
    print(f"本次基準化數量：{result.baseline_count}")


# 逐筆列出通過個人化篩選的公告。
def print_items(label: str, items: list[object]) -> None:
    print(label)
    if not items:
        print("- 無")
        return
    for item in items:
        print(f"- {item.published_date} | {item.title} | {item.eligibility_reason}")
        print(f"  {item.source_url}")


# 印出不修改資料庫的全部公告稽核結果。
def print_audit(result: AuditResult) -> None:
    print(f"稽核公告數量：{len(result.records)}")
    print(f"明確適合：{result.eligible_count}")
    print(f"資格待確認：{result.review_count}")
    print(f"不推播：{result.ineligible_count}")
    for record in result.records:
        _print_audit_record(record)
    print(result.message)


# 印出單筆公告判斷、正文摘要與來源附件診斷。
def _print_audit_record(record: AuditRecord) -> None:
    item = record.item
    print(f"- {item.published_date} | {item.notice_kind} | {item.eligibility_status}")
    print(f"  {item.title} | {item.eligibility_reason}")
    print(f"  正文摘要：{record.detail_excerpt or '無法擷取'}")
    for line in build_fetch_diagnostic_lines(record.fetch_result):
        print(line)
    print(f"  {item.source_url}")


# 判斷目前是否為會傳送 LINE 的正式模式。
def _is_live_mode(args: argparse.Namespace) -> bool:
    return not args.dry_run and not args.audit and not args.initialize_baseline


# 執行命令列流程，只有正式模式會驗證 LINE 設定。
def main(argv: list[str] | None = None) -> None:
    configure_console_output()
    args = parse_args(argv)
    if _is_live_mode(args):
        validate_settings()
    service = build_service(profile_required=not args.initialize_baseline)
    result = execute_service(args, service)
    if isinstance(result, AuditResult):
        print_audit(result)
        return
    print_summary(result)
    print_items("適合且待通知公告：", result.pending_items)
    print(result.message)


if __name__ == "__main__":
    main()
