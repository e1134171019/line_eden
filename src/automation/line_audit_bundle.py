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
from src.automation.pipeline_rejection_artifact import write_pipeline_rejection_artifact
from src.automation.source_health_artifact import write_source_health_artifact
from src.automation.structured_shadow_artifact import write_structured_shadow_artifacts
from src.notifiers.line_notifier import send_text_message
from src.runtime.run_mode import RunMode


def main() -> None:
    """執行完整 audit、輸出三類 artifact 並傳送 LINE。"""

    validate_settings()
    validate_gemini_settings()
    service = build_service(mode=RunMode.AUDIT, use_gemini=True)
    result = service.audit()
    csv_path, json_path = write_structured_shadow_artifacts(result)
    health_path = write_source_health_artifact(service.collector)
    rejection_path = write_pipeline_rejection_artifact(result)
    source_summary = getattr(service.collector, "source_summary_lines", lambda: [])()
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
    print(f"Structured JSON：{json_path}")
    print(f"來源健康：{health_path}")
    print(f"排除明細：{rejection_path}")
    print("真實檢查報告已傳送至 LINE。")


if __name__ == "__main__":
    main()
