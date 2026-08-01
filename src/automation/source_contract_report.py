# -*- coding: utf-8 -*-

from config import (
    HTTP_TIMEOUT_SECONDS,
    HTTP_USER_AGENT,
    LHU_SCHOLARSHIP_URL,
    SOURCE_FETCH_WORKERS,
    SOURCE_MAX_PAGES,
)
from src.automation.source_health_artifact import write_source_health_artifact
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.expanded_scholarship_collector import ExpandedScholarshipCollector


def main() -> None:
    """完整抓取七個 collector 群組，區分網站改版與程式退步。"""

    collector = ExpandedScholarshipCollector(
        LHU_SCHOLARSHIP_URL,
        HTTP_TIMEOUT_SECONDS,
        HTTP_USER_AGENT,
        CollectionMode.FULL_AUDIT,
        SOURCE_MAX_PAGES,
        SOURCE_FETCH_WORKERS,
    )
    records = collector.collect()
    path = write_source_health_artifact(collector)
    print(f"跨來源唯一公告：{len(records)}")
    for line in collector.source_summary_lines():
        print(line)
    print(f"來源健康 artifact：{path}")

    failed = [
        item
        for item in collector.diagnostics
        if item.status == "error" or item.completeness == "partial"
    ]
    if failed:
        labels = "、".join(item.source for item in failed)
        raise SystemExit(f"live contract 未通過：{labels}")


if __name__ == "__main__":
    main()
