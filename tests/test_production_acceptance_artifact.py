# -*- coding: utf-8 -*-

import csv
import json
from dataclasses import replace
from pathlib import Path

from src.automation.production_acceptance_artifact import (
    build_production_acceptance_rows,
    write_production_acceptance_artifacts,
)
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.models.scholarship import Scholarship
from src.services.scholarship_service import AuditRecord, AuditResult
from src.services.structured_shadow_comparison import StructuredShadowComparison


def _record() -> AuditRecord:
    item = Scholarship.from_raw(
        "tun-program-songliang-aid",
        "松樑助學金",
        "2026-08-02",
        "https://example.test/detail",
        program_id="songliang-aid",
    )
    item = replace(
        item,
        hard_eligibility_status="ineligible",
        eligibility_status="ineligible",
    )
    source = ResourceDiagnostic(
        "source",
        item.detail_url,
        "https://example.test/final-detail",
        "text/html",
        100,
        "html",
        "success",
        80,
    )
    attachment = ResourceDiagnostic(
        "attachment",
        "https://example.test/rules.pdf",
        "https://example.test/rules.pdf",
        "application/pdf",
        200,
        "pdf",
        "success",
        120,
    )
    fetch_result = DetailFetchResult(
        "rules",
        source,
        (attachment,),
        1,
        body_text="rules",
    )
    shadow = StructuredShadowComparison(
        "ineligible",
        "ineligible",
        False,
        "legacy",
        "structured",
        tuple(),
    )
    return AuditRecord(item, "rules", fetch_result, structured_shadow=shadow)


def _source_report() -> dict[str, object]:
    return {
        "program_states": [
            {
                "program_id": "songliang-aid",
                "title": "松樑助學金",
                "status": "matched",
                "entry_url": "https://example.test/list",
                "candidate_count": 1,
                "match_method": "exact_alias",
                "top_score": 100,
            },
            {
                "program_id": "empty-program",
                "title": "目前無公告",
                "status": "no_current_announcement",
                "entry_url": "https://example.test/empty",
            },
        ]
    }


def _audit_result() -> AuditResult:
    return AuditResult([_record()], 0, 0, 1, "audit")


def test_build_rows_combines_source_detail_attachment_and_decision() -> None:
    rows = build_production_acceptance_rows(_source_report(), _audit_result())
    songliang = rows[0]
    assert songliang["program_id"] == "songliang-aid"
    assert songliang["detail_urls"] == ["https://example.test/detail"]
    assert songliang["final_detail_urls"] == ["https://example.test/final-detail"]
    assert songliang["discovered_attachment_count"] == 1
    assert songliang["successful_attachment_count"] == 1
    assert songliang["legacy_final_statuses"] == ["ineligible"]
    assert songliang["structured_statuses"] == ["ineligible"]
    assert songliang["hard_conflict"] is False
    assert rows[1]["announcement_count"] == 0


def test_write_artifacts_outputs_json_and_csv(tmp_path: Path) -> None:
    json_path = tmp_path / "acceptance.json"
    csv_path = tmp_path / "acceptance.csv"
    written_json, written_csv = write_production_acceptance_artifacts(
        _source_report(),
        _audit_result(),
        json_path,
        csv_path,
    )
    assert written_json == json_path
    assert written_csv == csv_path
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(payload) == 2
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["program_id"] == "songliang-aid"
    assert json.loads(rows[0]["detail_urls"]) == ["https://example.test/detail"]
