# -*- coding: utf-8 -*-

from dataclasses import replace

import pytest

from src.automation.release_acceptance import evaluate_release_acceptance
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.models.scholarship import Scholarship
from src.services.scholarship_service import AuditRecord, AuditResult
from src.services.structured_shadow_comparison import StructuredShadowComparison


def _source_report(*, override: tuple[str, str] | None = None) -> dict[str, object]:
    program_ids = [f"program-{index}" for index in range(36)]
    program_ids.extend(["auden-university-talent", "songliang-aid"])
    states = [{"program_id": value, "status": "matched"} for value in program_ids]
    if override is not None:
        program_id, status = override
        next(item for item in states if item["program_id"] == program_id)["status"] = status
    return {"program_states": states}


def _fetch_result() -> DetailFetchResult:
    diagnostic = ResourceDiagnostic(
        "source",
        "https://example.test/detail",
        "https://example.test/detail",
        "text/html",
        100,
        "html",
        "success",
        100,
    )
    return DetailFetchResult("rules", diagnostic, tuple(), 0, body_text="rules")


def _record(
    program_id: str,
    hard_status: str,
    *,
    legacy_status: str = "",
    structured_status: str = "",
) -> AuditRecord:
    item = Scholarship.from_raw(
        f"tun-program-{program_id}",
        program_id,
        "2026-08-02",
        "https://example.test/detail",
        program_id=program_id,
    )
    item = replace(
        item,
        eligibility_status=hard_status,
        hard_eligibility_status=hard_status,
    )
    shadow = None
    if legacy_status and structured_status:
        shadow = StructuredShadowComparison(
            legacy_status,
            structured_status,
            legacy_status != structured_status,
            "legacy reason",
            "structured reason",
            tuple(),
        )
    return AuditRecord(item, "rules", _fetch_result(), structured_shadow=shadow)


def _audit_result(*records: AuditRecord) -> AuditResult:
    return AuditResult(list(records), 0, 0, 1, "audit")


def test_release_acceptance_passes_only_with_songliang_ineligible() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(_record("songliang-aid", "ineligible")),
    )
    assert result.passed is True
    result.require_passed()


def test_release_acceptance_blocks_bad_source_status() -> None:
    result = evaluate_release_acceptance(
        _source_report(override=("program-5", "matcher_miss")),
        _audit_result(_record("songliang-aid", "ineligible")),
    )
    assert result.passed is False
    assert "program-5 來源狀態為 matcher_miss" in result.failures


def test_release_acceptance_blocks_songliang_legacy_false_positive() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(_record("songliang-aid", "eligible")),
    )
    assert result.passed is False
    assert any("松樑最終狀態必須為 ineligible" in item for item in result.failures)


def test_release_acceptance_blocks_hard_evaluator_conflict() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record("songliang-aid", "ineligible"),
            _record(
                "conflict-program",
                "eligible",
                legacy_status="eligible",
                structured_status="ineligible",
            ),
        ),
    )
    assert result.passed is False
    assert any("evaluator 硬衝突" in item for item in result.failures)
    with pytest.raises(RuntimeError, match="Production 驗收未通過"):
        result.require_passed()
