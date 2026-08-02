# -*- coding: utf-8 -*-

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from src.collectors.expanded_scholarship_collector import ExpandedScholarshipCollector
from src.collectors.multi_source_collector import SourceDiagnostic
from src.collectors.tun_program_watch_collector import ProgramSourceState

SEVERE_PROGRAM_STATUSES = {
    "fetch_failed",
    "matcher_miss",
    "match_ambiguous",
    "wrong_source",
    "source_structure_changed",
    "application_portal",
    "pending_source",
}


# 建立單一來源 0~100 健康分數，與 URL 類型品質分開保存。
def source_health_score(item: SourceDiagnostic) -> int:
    if item.status == "error":
        return 0
    score = 30
    if item.completeness in {"complete", "incremental"}:
        score += 25
    elif item.completeness == "partial":
        score += 10
    if item.pages_requested:
        score += round(20 * item.pages_succeeded / item.pages_requested)
    else:
        score += 20
    if item.raw_rows:
        score += round(15 * item.parsed_rows / item.raw_rows)
    else:
        score += 15 if item.status != "empty" else 5
    if item.child_sources_detected:
        score += round(
            10 * item.child_sources_succeeded / item.child_sources_detected
        )
    else:
        score += 10
    return max(0, min(score, 100))


# 將分數映射為穩定狀態字串。
def source_health_status(score: int) -> str:
    if score >= 85:
        return "healthy"
    if score >= 60:
        return "degraded"
    if score >= 1:
        return "warning"
    return "failed"


# 建立七個群組與 38 項方案的機器可讀健康報告。
def build_source_health_report(
    collector: ExpandedScholarshipCollector,
) -> dict[str, Any]:
    multi = collector.multi_source
    sources = []
    for diagnostic in multi.diagnostics:
        score = source_health_score(diagnostic)
        record = asdict(diagnostic)
        record.update(
            {
                "health_score": score,
                "health_status": source_health_status(score),
            }
        )
        sources.append(record)
    programs = [
        _program_record(item)
        for item in (
            collector.tun_collector.program_states
            if collector.tun_collector is not None
            else tuple()
        )
    ]
    severe = [item for item in programs if item["status"] in SEVERE_PROGRAM_STATUSES]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "configured_source_groups": len(multi.collectors),
        "source_groups": sources,
        "program_count": len(programs),
        "program_states": programs,
        "severe_program_count": len(severe),
        "severe_program_ids": [item["program_id"] for item in severe],
    }


# ProgramSourceState 已包含 URL 類型、風險與 matcher 分數。
def _program_record(item: ProgramSourceState) -> dict[str, Any]:
    record = asdict(item)
    record["source_url_type"] = item.source_url_type.value
    record["update_risk"] = item.update_risk.value
    record["severe"] = item.status in SEVERE_PROGRAM_STATUSES
    return record


# 寫入 artifacts/source-health.json。
def write_source_health_artifact(
    collector: ExpandedScholarshipCollector,
    path: Path = Path("artifacts/source-health.json"),
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_source_health_report(collector), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
