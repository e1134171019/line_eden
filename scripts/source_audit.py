# -*- coding: utf-8 -*-

from config import (
    HTTP_TIMEOUT_SECONDS,
    HTTP_USER_AGENT,
    LHU_SCHOLARSHIP_URL,
    SOURCE_MAX_PAGES,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.lhu_collector import LhuCollector

EXPECTED_SOURCE_COUNT = 6


def main() -> None:
    """完整抓取六個來源，只輸出診斷，不讀 profile、DB 或 LINE Secrets。"""
    collector = LhuCollector(
        LHU_SCHOLARSHIP_URL,
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
        CollectionMode.FULL_AUDIT,
        SOURCE_MAX_PAGES,
    )
    records = collector.collect()
    diagnostics = collector.multi_source.diagnostics if collector.multi_source else []

    print("六來源完整性 smoke test")
    print(f"設定來源網站：{EXPECTED_SOURCE_COUNT}")
    print(f"實際來源診斷：{len(diagnostics)}")
    print(f"跨來源去重後公告：{len(records)}")
    for line in collector.source_summary_lines():
        print(f"- {line}")

    if len(diagnostics) != EXPECTED_SOURCE_COUNT:
        raise SystemExit("來源診斷數量不是 6，視為失敗。")
    incomplete = [
        item.source
        for item in diagnostics
        if item.status != "success" or item.completeness != "complete"
    ]
    if incomplete:
        raise SystemExit(f"來源尚未完整：{', '.join(incomplete)}")
    print("六個來源均完成完整抓取。")


if __name__ == "__main__":
    main()
