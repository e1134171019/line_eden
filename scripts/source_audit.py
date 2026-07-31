# -*- coding: utf-8 -*-

from config import (
    HTTP_TIMEOUT_SECONDS,
    HTTP_USER_AGENT,
    LHU_SCHOLARSHIP_URL,
    SOURCE_MAX_PAGES,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.expanded_scholarship_collector import ExpandedScholarshipCollector

EXPECTED_CORE_SOURCE_COUNT = 6
EXPECTED_SOURCE_GROUP_COUNT = 7
EXPECTED_PROGRAM_WATCH_COUNT = 38


def main() -> None:
    """完整抓取六個核心來源及 38 方案監測群組，只輸出來源診斷。"""
    collector = ExpandedScholarshipCollector(
        LHU_SCHOLARSHIP_URL,
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
        CollectionMode.FULL_AUDIT,
        SOURCE_MAX_PAGES,
    )
    records = collector.collect()
    diagnostics = collector.multi_source.diagnostics if collector.multi_source else []

    print("六核心來源＋38方案監測 smoke test")
    print(f"設定來源群組：{EXPECTED_SOURCE_GROUP_COUNT}")
    print(f"實際來源診斷：{len(diagnostics)}")
    print(f"跨來源去重後公告：{len(records)}")
    for line in collector.source_summary_lines():
        print(f"- {line}")

    if len(diagnostics) != EXPECTED_SOURCE_GROUP_COUNT:
        raise SystemExit("來源診斷數量不是 7，視為失敗。")

    core_incomplete = [
        item.source
        for item in diagnostics[:EXPECTED_CORE_SOURCE_COUNT]
        if item.status != "success" or item.completeness != "complete"
    ]
    if core_incomplete:
        raise SystemExit(f"核心來源尚未完整：{', '.join(core_incomplete)}")

    watch = diagnostics[-1]
    if watch.source != "TUN 38方案官方監測":
        raise SystemExit("第七個來源群組不是 TUN 38方案官方監測。")
    if watch.status != "success" or watch.completeness != "complete":
        raise SystemExit(f"38 方案分頁尚未完整：{watch.error or watch.stop_reason}")
    if watch.child_sources_detected != EXPECTED_PROGRAM_WATCH_COUNT:
        raise SystemExit("38 方案監測目錄數量不正確。")
    if watch.child_sources_succeeded != EXPECTED_PROGRAM_WATCH_COUNT:
        raise SystemExit("38 方案仍有入口無法連線。")

    print("六個核心來源均完成完整抓取。")
    print(
        "38 方案監測完成："
        f"方案 {watch.child_sources_succeeded}/{watch.child_sources_detected}，"
        f"分頁 {watch.pages_succeeded}/{watch.pages_detected}。"
    )


if __name__ == "__main__":
    main()
