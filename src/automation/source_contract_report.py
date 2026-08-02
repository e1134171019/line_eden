# -*- coding: utf-8 -*-

import json

from main import _build_collector
from src.automation.source_health_artifact import (
    SEVERE_PROGRAM_STATUSES,
    build_source_health_report,
    write_source_health_artifact,
)
from src.runtime.run_mode import RunMode


# 完整抓取七個來源群組，區分網站改版、錯誤入口與正常無公告。
def main() -> None:
    collector = _build_collector(RunMode.AUDIT)
    records = collector.collect()
    path = write_source_health_artifact(collector)
    report = build_source_health_report(collector)
    severe = report["severe_program_ids"]
    failed_groups = [
        item["source"]
        for item in report["source_groups"]
        if item["health_status"] == "failed"
    ]
    print(f"完整來源公告：{len(records)}")
    print(f"來源健康 artifact：{path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failed_groups:
        raise SystemExit(f"來源群組失敗：{', '.join(failed_groups)}")
    if severe:
        statuses = sorted(SEVERE_PROGRAM_STATUSES)
        raise SystemExit(
            f"TUN 方案有嚴重來源狀態：{', '.join(severe)}；嚴重類型：{statuses}"
        )


if __name__ == "__main__":
    main()
