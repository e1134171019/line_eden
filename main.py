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
    LINE_USER_ID,
    LINE_SUMMARY_BATCH_SIZE,
    SCHOLARSHIP_DB_FILENAME,
    SCHOLARSHIP_FILTER_KEYWORDS,
    validate_settings,
)
from src.collectors.lhu_collector import LhuCollector
from src.notifiers.line_notifier import send_text_message
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ScholarshipService, ServiceResult


# 解析命令列參數，並限制執行模式只能擇一。
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scholarship Agent 第二階段")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="只顯示資料，不傳 LINE")
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


# 建立公告蒐集、資料庫與通知服務。
def build_service() -> ScholarshipService:
    collector = LhuCollector(
        LHU_SCHOLARSHIP_URL,
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
    )
    repository = ScholarshipRepository(DATA_DIR / SCHOLARSHIP_DB_FILENAME)
    return ScholarshipService(
        collector,
        repository,
        build_notifier(),
        include_keywords=SCHOLARSHIP_FILTER_KEYWORDS,
        summary_batch_size=LINE_SUMMARY_BATCH_SIZE,
    )


# 依命令列模式執行服務，基準初始化不會傳送 LINE。
def execute_service(
    args: argparse.Namespace,
    service: ScholarshipService,
) -> ServiceResult:
    if args.initialize_baseline:
        return service.initialize_baseline()
    return service.run(dry_run=args.dry_run)


# 印出本次蒐集、待通知、已通知與基準化摘要。
def print_summary(result: ServiceResult) -> None:
    print(f"蒐集公告數量：{len(result.collected)}")
    print(f"待通知公告數量：{len(result.pending_items)}")
    print(f"本次通知數量：{result.notified_count}")
    print(f"本次基準化數量：{result.baseline_count}")


# 逐筆列出公告資料，方便 dry-run 檢查。
def print_items(label: str, items: list[object]) -> None:
    print(label)
    if not items:
        print("- 無")
        return
    for item in items:
        print(f"- {item.published_date} | {item.category} | {item.title} | {item.source_url}")


# 執行命令列流程，只有正式模式會驗證 LINE 設定。
def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.dry_run and not args.initialize_baseline:
        validate_settings()
    result = execute_service(args, build_service())
    print_summary(result)
    print_items("全部公告：", result.collected)
    print_items("待通知公告：", result.pending_items)
    print(result.message)


if __name__ == "__main__":
    main()
