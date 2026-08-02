# -*- coding: utf-8 -*-

from dataclasses import replace

import pytest

from src.automation.release_acceptance import evaluate_release_acceptance
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.models.scholarship import Scholarship
from src.services.scholarship_service import AuditRecord, AuditResult
from src.services.structured_shadow_comparison import StructuredShadowComparison

AUDEN = "auden-university-talent"
SONGLIANG = "songliang-aid"


def _source_report(*, override: tuple[str, str] | None = None) -> dict[str, object]:
    program_ids = [f"program-{index}" for index in range(36)]
    program_ids.extend([AUDEN, SONGLIANG])
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
    title: str | None = None,
    notice_kind: str = "policy",
    resolution_status: str = "valid_application_detail",
    action_status: str = "not_actionable",
    application_status: str | None = None,
    review_kind: str = "",
    reason: str = "",
    legacy_status: str = "",
    structured_status: str = "",
) -> AuditRecord:
    item = Scholarship.from_raw(
        f"tun-program-{program_id or 'unassigned'}",
        title or program_id,
        "2026-08-02",
        "https://example.test/detail",
        program_id=program_id,
    )
    resolved_application_status = application_status or (
        "not_applicable" if notice_kind == "policy" else "open"
    )
    item = replace(
        item,
        eligibility_status=hard_status,
        eligibility_reason=reason,
        hard_eligibility_status=hard_status,
        hard_eligibility_reason=reason,
        notice_kind=notice_kind,
        application_status=resolved_application_status,
        resolution_status=resolution_status,
        action_status=action_status,
        review_kind=review_kind,
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


def _audit_result(
    *records: AuditRecord,
    include_auden: bool = True,
) -> AuditResult:
    values = list(records)
    if include_auden and not any(record.item.program_id == AUDEN for record in values):
        values.append(
            _record(
                AUDEN,
                "eligible",
                notice_kind="application",
                action_status="apply_candidate",
            )
        )
    return AuditResult(values, 0, 0, 1, "audit")


def test_release_acceptance_allows_policy_ineligible_and_failed_form_review() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record(SONGLIANG, "ineligible"),
            _record(
                SONGLIANG,
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
                SONGLIANG,
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
            _record(SONGLIANG, "ineligible"),
            _record(
                SONGLIANG,
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
                SONGLIANG,
                "ineligible",
                notice_kind="application",
                action_status="apply_candidate",
            )
        ),
    )

    assert result.passed is False
    assert "松樑仍被列為可準備申請" in result.failures


def test_release_acceptance_requires_auden_eligible_candidate() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record(
                AUDEN,
                "ineligible",
                notice_kind="application",
                action_status="reject",
                reason="目前年級不在公告允許範圍。",
            ),
            _record(SONGLIANG, "ineligible"),
            include_auden=False,
        ),
    )

    assert result.passed is False
    assert any("耀登優秀人才" in failure for failure in result.failures)
    assert any("年級" in failure for failure in result.failures)


def test_release_acceptance_blocks_actionable_source_incomplete_review() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record(SONGLIANG, "ineligible"),
            _record(
                "incomplete-program",
                "review",
                notice_kind="application",
                resolution_status="insufficient_evidence",
                action_status="verify_source",
                review_kind="source_incomplete",
            ),
        ),
    )

    assert result.passed is False
    assert any("可行動公告來源不完整" in failure for failure in result.failures)


def test_authoritative_program_detail_dominates_duplicate_wrong_page() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record(SONGLIANG, "ineligible"),
            _record(
                "taishin-youth-volunteer",
                "ineligible",
                notice_kind="application",
            ),
            _record(
                "taishin-youth-volunteer",
                "review",
                title="網站地圖",
                notice_kind="application",
                resolution_status="navigation_or_wrong_page",
                action_status="verify_source",
                review_kind="source_incomplete",
            ),
        ),
    )

    assert result.passed is True


def test_known_program_title_deduplicates_unassigned_relay_record() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record(SONGLIANG, "ineligible"),
            _record(
                "cdf-vocational",
                "ineligible",
                notice_kind="application",
            ),
            _record(
                "",
                "review",
                title="財團法人中華開發文教基金會技藝職能獎學金",
                notice_kind="application",
                resolution_status="insufficient_evidence",
                action_status="verify_source",
                review_kind="source_incomplete",
            ),
        ),
    )

    assert result.passed is True


def test_complete_profile_review_dominates_duplicate_incomplete_page() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record(SONGLIANG, "ineligible"),
            _record(
                "ht-emergency",
                "review",
                notice_kind="application",
                action_status="manual_review",
                review_kind="profile_missing",
            ),
            _record(
                "ht-emergency",
                "review",
                title="慈善志業",
                notice_kind="application",
                resolution_status="navigation_or_wrong_page",
                action_status="verify_source",
                review_kind="source_incomplete",
            ),
        ),
    )

    assert result.passed is True


def test_resolved_structured_veto_is_not_a_remaining_hard_conflict() -> None:
    result = evaluate_release_acceptance(
        _source_report(),
        _audit_result(
            _record(
                SONGLIANG,
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
            _record(SONGLIANG, "ineligible"),
            _record(
                "conflict-program",
                "eligible",
                notice_kind="application",
                action_status="apply_candidate",
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
        _audit_result(_record(SONGLIANG, "ineligible")),
    )

    assert result.passed is False
    assert "program-5 來源狀態為 matcher_miss" in result.failures
