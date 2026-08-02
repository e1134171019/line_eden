# -*- coding: utf-8 -*-

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from src.evaluators.notice_classifier import APPLICATION
from src.evaluators.runtime_safety import EXPIRED, STALE_UNKNOWN
from src.services.scholarship_service import AuditResult


@dataclass(frozen=True)
class PipelineRejection:
    """單筆公告在指定階段不再進入後續行動的原因。"""

    source: str
    program_id: str
    title: str
    entry_url: str
    detail_url: str
    stage: str
    reason: str


# 從 relevance、公告分類、期間與硬性資格建立逐筆排除帳本。
def build_pipeline_rejections(result: AuditResult) -> list[PipelineRejection]:
    records = [
        PipelineRejection(
            item.item.source,
            item.item.program_id,
            item.item.title,
            item.item.entry_url,
            item.item.detail_url,
            item.stage,
            item.reason,
        )
        for item in result.exclusions
    ]
    for record in result.records:
        item = record.item
        if item.notice_kind != APPLICATION:
            records.append(
                _record(item, "notice_classification", item.exclusion_reason or item.eligibility_reason)
            )
            continue
        if item.application_status in {EXPIRED, STALE_UNKNOWN}:
            records.append(
                _record(item, "application_period", item.exclusion_reason or item.eligibility_reason)
            )
            continue
        hard_status = item.hard_eligibility_status or item.eligibility_status
        if hard_status == "ineligible":
            records.append(
                _record(item, "hard_eligibility", item.hard_eligibility_reason or item.eligibility_reason)
            )
    return records


# 將 Scholarship 欄位轉為 rejection ledger。
def _record(item: object, stage: str, reason: str) -> PipelineRejection:
    return PipelineRejection(
        str(getattr(item, "source", "")),
        str(getattr(item, "program_id", "")),
        str(getattr(item, "title", "")),
        str(getattr(item, "entry_url", "")),
        str(getattr(item, "detail_url", "")),
        stage,
        reason or "未提供排除原因",
    )


# 寫入 artifacts/pipeline-rejections.json。
def write_pipeline_rejection_artifact(
    result: AuditResult,
    path: Path = Path("artifacts/pipeline-rejections.json"),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": 0,
        "records": [],
    }
    records = build_pipeline_rejections(result)
    payload["count"] = len(records)
    payload["records"] = [asdict(item) for item in records]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
