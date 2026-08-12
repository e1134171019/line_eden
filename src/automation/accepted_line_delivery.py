# -*- coding: utf-8 -*-

from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    HTTP_TIMEOUT_SECONDS,
    LINE_API_URL,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_USER_ID,
    validate_gemini_settings,
    validate_settings,
)
from main import build_service
from src.automation.eligible_line_links import (
    MAX_VISIBLE_LINKS,
    EligibleLink,
    build_line_message,
)
from src.automation.pipeline_rejection_artifact import write_pipeline_rejection_artifact
from src.automation.production_acceptance_artifact import (
    write_production_acceptance_artifacts,
)
from src.automation.production_acceptance_audit import _ReplayProgramCollector
from src.automation.release_acceptance import evaluate_release_acceptance
from src.automation.source_health_artifact import (
    build_source_health_report,
    write_source_health_artifact,
)
from src.automation.structured_shadow_artifact import write_structured_shadow_artifacts
from src.collectors.expanded_scholarship_collector import ExpandedScholarshipCollector
from src.evaluators.eligibility_evaluator import ELIGIBLE
from src.models.eligibility_axes import APPLY_CANDIDATE
from src.notifiers.line_notifier import send_text_message
from src.runtime.run_mode import RunMode
from src.services.scholarship_service import AuditRecord

MAX_LINE_TEXT_LENGTH = 4800
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")


def links_from_accepted_records(records: list[AuditRecord]) -> tuple[EligibleLink, ...]:
    """從同一次 production audit 擷取真正可申請的 LINE 連結。"""

    links: list[EligibleLink] = []
    seen_urls: set[str] = set()
    for record in records:
        item = record.item
        hard_status = item.hard_eligibility_status or item.eligibility_status
        if hard_status != ELIGIBLE or item.action_status != APPLY_CANDIDATE:
            continue
        title = item.title.strip()
        url = (item.detail_url or item.source_url).strip()
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        links.append(EligibleLink(title=title, url=url))
    return tuple(links)


def main() -> None:
    """同一輪完成 production acceptance，通過後才正式傳送動態 LINE。"""

    validate_settings()
    validate_gemini_settings()
    service = build_service(mode=RunMode.AUDIT, use_gemini=True)
    if not isinstance(service.collector, ExpandedScholarshipCollector):
        raise RuntimeError("Formal LINE delivery 需要 ExpandedScholarshipCollector")

    source_collector = service.collector
    print("Formal LINE delivery：開始完整來源契約收集", flush=True)
    raw_items = source_collector.collect()
    source_report = build_source_health_report(source_collector)
    source_health = write_source_health_artifact(source_collector)
    program_items = [
        item
        for item in raw_items
        if item.program_id or item.source.startswith("tun-program-")
    ]
    print(
        "Formal LINE delivery：完整來源收集完成，"
        f"共 {len(raw_items)} 筆；38 方案候選 {len(program_items)} 筆",
        flush=True,
    )

    service.collector = _ReplayProgramCollector(program_items)
    print("Formal LINE delivery：開始逐方案正文、附件與資格證據驗收", flush=True)
    result = service.audit()
    print(
        f"Formal LINE delivery：完成 {len(result.records)} 筆逐方案語意驗收",
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

    links = links_from_accepted_records(result.records)
    message = build_line_message(
        links,
        checked_at=datetime.now(TAIPEI_TIMEZONE),
        max_length=MAX_LINE_TEXT_LENGTH,
        collected_count=len(raw_items),
    )
    send_text_message(
        api_url=LINE_API_URL,
        channel_access_token=LINE_CHANNEL_ACCESS_TOKEN,
        user_id=LINE_USER_ID,
        text=message,
        timeout_seconds=HTTP_TIMEOUT_SECONDS,
    )
    print(message)
    print(
        "正式 LINE 已傳送："
        f"{min(len(links), MAX_VISIBLE_LINKS)} 筆動態 apply_candidate。"
    )


if __name__ == "__main__":
    main()
