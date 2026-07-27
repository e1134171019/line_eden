# -*- coding: utf-8 -*-

import argparse
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
    NOTIFY_REVIEW_ITEMS,
    PROFILE_PATH,
    SCHOLARSHIP_DB_FILENAME,
    SCHOLARSHIP_FILTER_KEYWORDS,
    validate_settings,
)
from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.collectors.lhu_collector import LhuCollector
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.notifiers.line_notifier import send_text_message
from src.profiles.student_profile import load_student_profile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ScholarshipService, ServiceResult


# 解析命令列參數，並限制執行模式只能擇一。
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scholarship Agent 第三階段")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="評估適合度但不傳 LINE")
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


# 需要個人化判斷時建立公告內頁擷取器。
def _build_detail_fetcher(
    profile_required: bool,
) -> AnnouncementDetailFetcher | None:
    if not profile_required:
        return None
    return AnnouncementDetailFetcher(HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT)


# 依命令列模式執行服務，基準初始化不會傳送 LINE。
def execute_service(
    args: argparse.Namespace,
    service: ScholarshipService,
) -> ServiceResult:
    if args.initialize_baseline:
        return service.initialize_baseline()
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


# 執行命令列流程，正式模式才驗證 LINE 設定。
def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.dry_run and not args.initialize_baseline:
        validate_settings()
    service = build_service(profile_required=not args.initialize_baseline)
    result = execute_service(args, service)
    print_summary(result)
    print_items("適合且待通知公告：", result.pending_items)
    print(result.message)


if __name__ == "__main__":
    main()
