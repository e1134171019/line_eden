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
    SCHOLARSHIP_FILTER_KEYWORDS,
    SCHOLARSHIP_DB_FILENAME,
    validate_settings,
)
from src.collectors.lhu_collector import LhuCollector
from src.notifiers.line_notifier import send_text_message
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ScholarshipService


# 解析命令列參數，支援 dry-run 模式。
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scholarship Agent 第二階段")
    parser.add_argument("--dry-run", action="store_true", help="只顯示資料，不傳 LINE")
    return parser.parse_args()


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


# 印出本次蒐集與新公告摘要。
def print_summary(collected_count: int, new_count: int) -> None:
    print(f"蒐集公告數量：{collected_count}")
    print(f"新公告數量：{new_count}")


# 逐筆列出公告資料，方便 dry-run 檢查。
def print_items(label: str, items: list[object]) -> None:
    print(label)
    if not items:
        print("- 無")
        return
    for item in items:
        print(f"- {item.published_date} | {item.category} | {item.title} | {item.source_url}")


# 執行獎學金公告蒐集、去重與通知流程。
def main() -> None:
    args = parse_args()
    if not args.dry_run:
        validate_settings()
    collector = LhuCollector(LHU_SCHOLARSHIP_URL, HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT)
    repository = ScholarshipRepository(DATA_DIR / SCHOLARSHIP_DB_FILENAME)
    service = ScholarshipService(
        collector,
        repository,
        build_notifier(),
        include_keywords=SCHOLARSHIP_FILTER_KEYWORDS,
    )
    result = service.run(dry_run=args.dry_run)
    print_summary(len(result.collected), len(result.new_items))
    print_items("全部公告：", result.collected)
    print_items("新公告：", result.new_items)
    print(result.message)


if __name__ == "__main__":
    main()
