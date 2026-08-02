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


def _fetch_result(*, source_status: str = "success") -> DetailFetchResult:
    diagnostic = ResourceDiagnostic(
        "source",
        "https://example.test/detail",
        "https://example.test/detail",
        "text/html",
        100,
        "html",
        source_status,
        100,
    )
    return DetailFetchResult("rules", diagnostic, tuple(), 0, body_text="rules")


def _record(
    program_id: str,
    hard_status: str,
    *,
    notice_kind: str = "policy",
    resolution_status: str = "valid_application_detail",
    action_status: str = "not_actionable",
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
        notice_kind=notice_kind,
        application_status="not_applicable" if notice_kind == "policy" else "open",
        resolution_status=resolution_status,
        action_status=action_status,
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


def test_release_acceptance_allows_policy_ineligible_and_failed_form_review() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record("songliang-aid", "ineligible"),
            _record(
                "songliang-aid",
                "review",
                notice_kind="unknown",
                resolution_status="source_error",
                action_status="verify_source",
            ),
        ),
    )

    assert result.passed is True
    result.require_passed()


def test_release_acceptance_requires_authoritative_songliang_rules() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record(
                "songliang-aid",
                "review",
                resolution_status="source_error",
                action_status="verify_source",
            )
        ),
    )

    assert result.passed is False
    assert any("沒有可驗證" in failure for failure in result.failures)


def test_release_acceptance_blocks_songliang_application_false_positive() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record("songliang-aid", "ineligible"),
            _record(
                "songliang-aid",
                "eligible",
                notice_kind="application",
                action_status="verify_source",
            ),
        ),
    )

    assert result.passed is False
    assert "松樑仍有 application 記錄被判定為 eligible" in result.failures


def test_release_acceptance_blocks_apply_candidate() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record(
                "songliang-aid",
                "ineligible",
                notice_kind="application",
                action_status="apply_candidate",
            )
        ),
    )

    assert result.passed is False
    assert "松樑仍被列為可準備申請" in result.failures


def test_resolved_structured_veto_is_not_a_remaining_hard_conflict() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record(
                "songliang-aid",
                "ineligible",
                legacy_status="eligible",
                structured_status="ineligible",
            )
        ),
    )

    assert result.passed is True


def test_unresolved_hard_conflict_blocks_release() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record("songliang-aid", "ineligible"),
            _record(
                "conflict-program",
                "eligible",
                notice_kind="application",
                legacy_status="eligible",
                structured_status="ineligible",
            ),
        ),
    )

    assert result.passed is False
    assert any("硬衝突未由 ineligible veto 解決" in item for item in result.failures)
    with pytest.raises(RuntimeError, match="Production 驗收未通過"):
        result.require_passed()


def test_bad_source_status_blocks_release() -> None:
    result = evaluate_release_acceptance(
        _source_report(override=("program-5", "matcher_miss")),
        _audit_result(_record("songliang-aid", "ineligible")),
    )

    assert result.passed is False
    assert "program-5 來源狀態為 matcher_miss" in result.failures
