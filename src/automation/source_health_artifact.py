# -*- coding: utf-8 -*-

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def write_source_health_artifact(
    collector: object,
    output_dir: Path = Path("artifacts"),
) -> Path:
    """將 MultiSourceCollector 診斷與 TUN 逐方案狀態輸出為 JSON。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    diagnostics = getattr(collector, "diagnostics", [])
    source_rows = [_source_payload(item) for item in diagnostics]
    program_rows = []
    for child in getattr(collector, "collectors", []):
        for state in getattr(child, "program_states", []):
            program_rows.append(asdict(state))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "overall_health": _overall_health(source_rows),
        "sources": source_rows,
        "programs": program_rows,
    }
    path = output_dir / "source-health.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _source_payload(item: object) -> dict[str, Any]:
    raw = asdict(item) if hasattr(item, "__dataclass_fields__") else vars(item)
    payload = dict(raw)
    payload["health_score"] = _health_score(payload)
    payload["health_status"] = _health_status(payload["health_score"])
    return payload


def _health_score(item: dict[str, Any]) -> int:
    score = 100
    status = str(item.get("status", "unknown"))
    completeness = str(item.get("completeness", "unknown"))
    if status == "error":
        return 0
    if status == "empty":
        score -= 35
    if status == "partial" or completeness == "partial":
        score -= 30
    pages_requested = int(item.get("pages_requested", 0) or 0)
    pages_succeeded = int(item.get("pages_succeeded", 0) or 0)
    if pages_requested:
        score -= round(30 * max(pages_requested - pages_succeeded, 0) / pages_requested)
    raw_rows = int(item.get("raw_rows", 0) or 0)
    rejected_rows = int(item.get("rejected_rows", 0) or 0)
    if raw_rows:
        score -= min(round(20 * rejected_rows / raw_rows), 20)
    if item.get("error"):
        score -= 10
    return max(min(score, 100), 0)


def _health_status(score: int) -> str:
    if score >= 90:
        return "healthy"
    if score >= 70:
        return "degraded"
    if score >= 40:
        return "warning"
    return "failed"


def _overall_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [int(row["health_score"]) for row in rows]
    score = round(sum(scores) / len(scores)) if scores else 0
    return {
        "score": score,
        "status": _health_status(score),
        "source_count": len(rows),
        "failed_count": sum(row["health_status"] == "failed" for row in rows),
        "warning_count": sum(row["health_status"] == "warning" for row in rows),
    }
