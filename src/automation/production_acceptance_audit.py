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
from src.collectors.expanded_scholarship_collector import ExpandedScholarshipCollector
from src.runtime.run_mode import RunMode


def main() -> None:
    """以正式狀態與 profile 驗收 detail/evaluator，但禁止傳送 LINE。"""

    validate_gemini_settings()
    service = build_service(mode=RunMode.AUDIT, use_gemini=True)
    result = service.audit()
    if not isinstance(service.collector, ExpandedScholarshipCollector):
        raise RuntimeError("Production acceptance 需要 ExpandedScholarshipCollector")

    structured_csv, structured_json = write_structured_shadow_artifacts(result)
    source_report = build_source_health_report(service.collector)
    source_health = write_source_health_artifact(service.collector)
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
