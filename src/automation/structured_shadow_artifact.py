# -*- coding: utf-8 -*-

import csv
import json
from pathlib import Path

from src.services.scholarship_service import AuditRecord, AuditResult

CSV_NAME = "structured-shadow-audit.csv"
JSON_NAME = "structured-shadow-audit.json"


def write_structured_shadow_artifacts(
    result: AuditResult,
    output_dir: Path = Path("artifacts"),
) -> tuple[Path, Path]:
    """輸出不含 profile 原始內容的來源、正文與 shadow 比較明細。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / CSV_NAME
    json_path = output_dir / JSON_NAME
    rows = [_record_payload(record) for record in result.records]
    _write_csv(csv_path, rows)
    summary = {
        "record_count": len(result.records),
        "legacy": {
            "eligible": result.eligible_count,
            "review": result.review_count,
            "ineligible": result.ineligible_count,
        },
        "review_kinds": _review_kind_counts(result.records),
        "resolution_statuses": _resolution_counts(result.records),
        "application_statuses": _application_status_counts(result.records),
        "structured": {
            "evaluated": result.structured_evaluated_count,
            "changed": result.structured_changed_count,
            "budget_deferred": result.structured_deferred_count,
            "errors": result.structured_error_count,
        },
        "records": rows,
    }
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return csv_path, json_path


def _review_kind_counts(records: list[AuditRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        kind = record.item.review_kind
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
    return counts


def _resolution_counts(records: list[AuditRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        status = record.item.resolution_status or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _application_status_counts(records: list[AuditRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        status = record.item.application_status or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _record_payload(record: AuditRecord) -> dict[str, object]:
    shadow = record.structured_shadow
    diagnostic = record.structured_gemini_diagnostic
    conditions = []
    if shadow:
        conditions = [
            {
                "field": item.field,
                "requirement": item.requirement,
                "status": item.status,
                "reason": item.reason,
            }
            for item in shadow.conditions
        ]
    item = record.item
    return {
        "published_date": item.published_date,
        "title": item.title,
        "source": item.source,
        "source_url": item.source_url,
        "entry_url": item.entry_url,
        "detail_url": item.detail_url,
        "program_id": item.program_id,
        "match_method": item.match_method,
        "match_score": item.match_score,
        "matched_alias": item.matched_alias,
        "detail_evidence_score": item.detail_evidence_score,
        "resolution_status": item.resolution_status,
        "notice_kind": item.notice_kind,
        "application_status": item.application_status,
        "rules_status": record.fetch_result.rules_status,
        "legacy_status": item.eligibility_status,
        "legacy_reason": item.eligibility_reason,
        "legacy_manual_checks": list(item.manual_checks),
        "legacy_review_kind": item.review_kind,
        "shadow_status": record.shadow_status,
        "structured_status": shadow.structured_status if shadow else "",
        "structured_reason": shadow.structured_reason if shadow else "",
        "changed": shadow.changed if shadow else False,
        "conditions": conditions,
        "gemini_status": diagnostic.status if diagnostic else "",
        "gemini_message": diagnostic.message if diagnostic else "",
        "gemini_cache_hit": diagnostic.cache_hit if diagnostic else False,
        "gemini_input_tokens": diagnostic.input_tokens if diagnostic else 0,
        "gemini_output_tokens": diagnostic.output_tokens if diagnostic else 0,
        "body_text_length": len(record.fetch_result.body_text),
        "eligibility_text_length": len(record.fetch_result.eligibility_text()),
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "published_date",
        "title",
        "source",
        "source_url",
        "entry_url",
        "detail_url",
        "program_id",
        "match_method",
        "match_score",
        "matched_alias",
        "detail_evidence_score",
        "resolution_status",
        "notice_kind",
        "application_status",
        "rules_status",
        "legacy_status",
        "legacy_reason",
        "legacy_manual_checks",
        "legacy_review_kind",
        "shadow_status",
        "structured_status",
        "structured_reason",
        "changed",
        "conditions",
        "gemini_status",
        "gemini_message",
        "gemini_cache_hit",
        "gemini_input_tokens",
        "gemini_output_tokens",
        "body_text_length",
        "eligibility_text_length",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            for field in ("conditions", "legacy_manual_checks"):
                csv_row[field] = json.dumps(
                    row[field],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            writer.writerow(csv_row)
