# -*- coding: utf-8 -*-

import csv
import json
from pathlib import Path
from typing import Any

from src.services.scholarship_service import AuditRecord, AuditResult

JSON_PATH = Path("artifacts/production-acceptance.json")
CSV_PATH = Path("artifacts/production-acceptance.csv")


def build_production_acceptance_rows(
    source_report: dict[str, Any],
    audit_result: AuditResult,
) -> list[dict[str, Any]]:
    records_by_program = _records_by_program(audit_result.records)
    rows = []
    for state in source_report.get("program_states", []):
        if not isinstance(state, dict):
            continue
        program_id = str(state.get("program_id", ""))
        records = records_by_program.get(program_id, [])
        rows.append(_build_row(state, records))
    return rows


def _records_by_program(records: list[AuditRecord]) -> dict[str, list[AuditRecord]]:
    grouped: dict[str, list[AuditRecord]] = {}
    for record in records:
        if record.item.program_id:
            grouped.setdefault(record.item.program_id, []).append(record)
    return grouped


def _build_row(
    state: dict[str, Any],
    records: list[AuditRecord],
) -> dict[str, Any]:
    detail_urls = _unique(
        record.item.detail_url or record.item.source_url for record in records
    )
    final_urls = _unique(record.fetch_result.source.final_url for record in records)
    legacy_statuses = _unique(_hard_status(record) for record in records)
    structured_statuses = _unique(
        record.structured_shadow.structured_status
        for record in records
        if record.structured_shadow is not None
    )
    return {
        "program_id": str(state.get("program_id", "")),
        "title": str(state.get("title", "")),
        "source_status": str(state.get("status", "")),
        "entry_url": str(state.get("entry_url", "")),
        "candidate_count": int(state.get("candidate_count", 0) or 0),
        "match_method": str(state.get("match_method", "")),
        "top_score": int(state.get("top_score", 0) or 0),
        "detail_urls": detail_urls,
        "final_detail_urls": final_urls,
        "announcement_count": len(records),
        "discovered_attachment_count": sum(
            record.fetch_result.discovered_attachment_count for record in records
        ),
        "successful_attachment_count": sum(
            record.fetch_result.successful_attachment_count() for record in records
        ),
        "legacy_final_statuses": legacy_statuses,
        "structured_statuses": structured_statuses,
        "hard_conflict": any(_hard_conflict(record) for record in records),
    }


def _hard_status(record: AuditRecord) -> str:
    return record.item.hard_eligibility_status or record.item.eligibility_status


def _hard_conflict(record: AuditRecord) -> bool:
    shadow = record.structured_shadow
    if shadow is None:
        return False
    return {shadow.legacy_status, shadow.structured_status} == {
        "eligible",
        "ineligible",
    }


def _unique(values: Any) -> list[str]:
    return sorted({str(value) for value in values if str(value).strip()})


def write_production_acceptance_artifacts(
    source_report: dict[str, Any],
    audit_result: AuditResult,
    json_path: Path = JSON_PATH,
    csv_path: Path = CSV_PATH,
) -> tuple[Path, Path]:
    rows = build_production_acceptance_rows(source_report, audit_result)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fieldnames = list(rows[0]) if rows else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: json.dumps(value, ensure_ascii=False)
                        if isinstance(value, list)
                        else value
                        for key, value in row.items()
                    }
                )
    return json_path, csv_path
