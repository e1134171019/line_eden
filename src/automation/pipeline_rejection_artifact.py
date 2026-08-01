# -*- coding: utf-8 -*-

from datetime import datetime, timezone
import json
from pathlib import Path

from src.evaluators.eligibility_evaluator import INELIGIBLE
from src.evaluators.runtime_safety import EXPIRED, STALE_UNKNOWN
from src.services.scholarship_service import AuditResult


def write_pipeline_rejection_artifact(
    result: AuditResult,
    output_dir: Path = Path("artifacts"),
) -> Path:
    """輸出每一筆真正排除或降級公告的 stage 與原因。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "source": item.item.source,
            "program_id": item.item.program_id,
            "title": item.item.title,
            "entry_url": item.item.entry_url,
            "detail_url": item.item.detail_url,
            "stage": item.stage,
            "reason": item.reason,
        }
        for item in result.exclusions
    ]
    for record in result.records:
        item = record.item
        stage = _record_stage(item.notice_kind, item.application_status, item.eligibility_status)
        if not stage:
            continue
        rows.append(
            {
                "source": item.source,
                "program_id": item.program_id,
                "title": item.title,
                "entry_url": item.entry_url,
                "detail_url": item.detail_url,
                "stage": stage,
                "reason": item.exclusion_reason or item.eligibility_reason,
            }
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(rows),
        "rejections": rows,
    }
    path = output_dir / "pipeline-rejections.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _record_stage(notice_kind: str, application_status: str, eligibility_status: str) -> str:
    if notice_kind != "application":
        return "non_application"
    if application_status == EXPIRED:
        return "expired"
    if application_status == STALE_UNKNOWN:
        return "stale_unknown"
    if eligibility_status == INELIGIBLE:
        return "hard_ineligible"
    return ""
