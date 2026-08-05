# -*- coding: utf-8 -*-

from config import validate_gemini_settings
from main import build_service
from src.automation.pipeline_rejection_artifact import (
    write_pipeline_rejection_artifact,
)
from src.automation.production_acceptance_artifact import (
    write_production_acceptance_artifacts,
)
from src.automation.release_acceptance import evaluate_release_acceptance
from src.automation.source_health_artifact import (
    build_source_health_report,
    write_source_health_artifact,
)
from src.automation.structured_shadow_artifact import write_structured_shadow_artifacts
from src.collectors.base_collector import BaseCollector
from src.collectors.expanded_scholarship_collector import ExpandedScholarshipCollector
from src.models.scholarship import Scholarship
from src.runtime.run_mode import RunMode


class _ReplayProgramCollector(BaseCollector):
    """重播 full collector 已取得的 38 方案候選，不再次存取外部網站。"""

    def __init__(self, items: list[Scholarship]) -> None:
        self._items = items

    def collect(self) -> list[Scholarship]:
        return list(self._items)


def main() -> None:
    """以正式狀態與 profile 驗收 38 方案，但禁止傳送 LINE。"""

    print("Production acceptance：開始 full source + 38-program semantic audit（禁止 LINE）", flush=True)
    validate_gemini_settings()
    service = build_service(mode=RunMode.AUDIT, use_gemini=True)
    if not isinstance(service.collector, ExpandedScholarshipCollector):
        raise RuntimeError("Production acceptance 需要 ExpandedScholarshipCollector")

    source_collector = service.collector
    print("Production acceptance：開始完整來源契約收集", flush=True)
    raw_items = source_collector.collect()
    source_report = build_source_health_report(source_collector)
    source_health = write_source_health_artifact(source_collector)
    program_items = [
        item
        for item in raw_items
        if item.program_id or item.source.startswith("tun-program-")
    ]
    print(
        "Production acceptance：完整來源收集完成，"
        f"共 {len(raw_items)} 筆；38 方案候選 {len(program_items)} 筆",
        flush=True,
    )

    service.collector = _ReplayProgramCollector(program_items)
    print("Production acceptance：開始逐方案正文、附件與資格證據驗收", flush=True)
    result = service.audit()
    print(
        f"Production acceptance：完成 {len(result.records)} 筆逐方案語意驗收",
        flush=True,
    )

    structured_csv, structured_json = write_structured_shadow_artifacts(result)
    rejections = write_pipeline_rejection_artifact(result)
    acceptance_json, acceptance_csv = write_production_acceptance_artifacts(
        source_report,
        result,
    )
    acceptance = evaluate_release_acceptance(source_report, result)

    print(f"Structured CSV：{structured_csv}")
    print(f"Structured JSON：{structured_json}")
    print(f"來源健康：{source_health}")
    print(f"管線排除：{rejections}")
    print(f"逐方案驗收 JSON：{acceptance_json}")
    print(f"逐方案驗收 CSV：{acceptance_csv}")
    if acceptance.passed:
        print("Production acceptance：PASS")
    else:
        print("Production acceptance：FAIL")
        for failure in acceptance.failures:
            print(f"- {failure}")
    acceptance.require_passed()


if __name__ == "__main__":
    main()
