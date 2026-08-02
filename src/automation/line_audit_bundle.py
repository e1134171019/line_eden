# -*- coding: utf-8 -*-

from config import (
    HTTP_TIMEOUT_SECONDS,
    LINE_API_URL,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_USER_ID,
    validate_gemini_settings,
    validate_settings,
)
from main import build_service
from src.automation.line_audit_report import build_report_message
from src.automation.pipeline_rejection_artifact import (
    write_pipeline_rejection_artifact,
)
from src.automation.source_health_artifact import write_source_health_artifact
from src.automation.structured_shadow_artifact import write_structured_shadow_artifacts
from src.collectors.expanded_scholarship_collector import ExpandedScholarshipCollector
from src.notifiers.line_notifier import send_text_message
from src.runtime.run_mode import RunMode
from src.services.structured_ineligible_veto import apply_veto_to_audit_result


# 一次產生 LINE、structured、source health 與 rejection 四組輸出。
def main() -> None:
    validate_settings()
    validate_gemini_settings()
    service = build_service(mode=RunMode.AUDIT, use_gemini=True)
    result = apply_veto_to_audit_result(service.audit())
    if not isinstance(service.collector, ExpandedScholarshipCollector):
        raise RuntimeError("LINE audit bundle 需要 ExpandedScholarshipCollector")

    csv_path, structured_json = write_structured_shadow_artifacts(result)
    source_health = write_source_health_artifact(service.collector)
    rejections = write_pipeline_rejection_artifact(result)
    source_summary = service.collector.source_summary_lines()
    message = build_report_message(result, source_summary)
    send_text_message(
        api_url=LINE_API_URL,
        channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
        user_id=LINE_USER_ID,
        text=message,
        timeout_seconds=HTTP_TIMEOUT_SECONDS,
    )
    print(message)
    print(f"Structured CSV：{csv_path}")
    print(f"Structured JSON：{structured_json}")
    print(f"來源健康：{source_health}")
    print(f"管線排除：{rejections}")
    print("真實檢查報告與 audit artifacts 已完成。")


if __name__ == "__main__":
    main()
