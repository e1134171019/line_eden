# -*- coding: utf-8 -*-

from dataclasses import replace

from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    EligibilityDecision,
)
from src.evaluators.notice_classifier import APPLICATION
from src.evaluators.runtime_safety import EXPIRED, STALE_UNKNOWN
from src.evaluators.structured_eligibility_evaluator import FAIL
from src.models.eligibility_axes import (
    APPLY_CANDIDATE,
    MANUAL_REVIEW,
    VERIFY_SOURCE,
    derive_action_status,
)
from src.services.scholarship_service import (
    AuditRecord,
    AuditResult,
    EvaluationOutcome,
)
from src.services.structured_shadow_comparison import StructuredShadowComparison

_ACTIONABLE_STATUSES = {APPLY_CANDIDATE, VERIFY_SOURCE, MANUAL_REVIEW}
_NON_ACTIONABLE_PERIODS = {EXPIRED, STALE_UNKNOWN}


# Structured 只能以明確失敗條件否決假符合，不得反向提升 legacy。
def should_apply_structured_ineligible_veto(
    legacy_status: str,
    shadow: StructuredShadowComparison | None,
) -> bool:
    if shadow is None or legacy_status not in {ELIGIBLE, REVIEW}:
        return False
    if shadow.structured_status != INELIGIBLE:
        return False
    return any(condition.status == FAIL for condition in shadow.conditions)


# 正式日常通知使用的單筆 outcome 否決。
def apply_veto_to_outcome(
    outcome: EvaluationOutcome,
    shadow: StructuredShadowComparison | None,
) -> EvaluationOutcome:
    if not should_apply_structured_ineligible_veto(outcome.decision.status, shadow):
        return outcome
    assert shadow is not None
    decision = EligibilityDecision(
        INELIGIBLE,
        (shadow.structured_reason,),
        outcome.decision.manual_checks,
    )
    action_status = derive_action_status(
        decision.status,
        outcome.evidence.status,
        outcome.notice_kind,
        outcome.application_status,
    )
    return replace(outcome, decision=decision, action_status=action_status)


# Audit 保留 shadow 差異，同時將最終 LINE／artifact 狀態套用否決結果。
def apply_veto_to_audit_result(result: AuditResult) -> AuditResult:
    records = [_apply_veto_to_record(record) for record in result.records]
    eligible = sum(_hard_status(record) == ELIGIBLE for record in records)
    review = sum(_hard_status(record) == REVIEW for record in records)
    ineligible = sum(_hard_status(record) == INELIGIBLE for record in records)
    pipeline = replace(
        result.pipeline_counts,
        notifiable=sum(_is_notifiable(record) for record in records),
    )
    return replace(
        result,
        records=records,
        eligible_count=eligible,
        review_count=review,
        ineligible_count=ineligible,
        pipeline_counts=pipeline,
    )


# 將單筆 audit item 的硬性狀態、理由與 action 一致更新。
def _apply_veto_to_record(record: AuditRecord) -> AuditRecord:
    legacy_status = _hard_status(record)
    shadow = record.structured_shadow
    if not should_apply_structured_ineligible_veto(legacy_status, shadow):
        return record
    assert shadow is not None
    item = record.item
    action_status = derive_action_status(
        INELIGIBLE,
        item.resolution_status,
        item.notice_kind,
        item.application_status,
    )
    updated = replace(
        item,
        eligibility_status=INELIGIBLE,
        eligibility_reason=shadow.structured_reason,
        hard_eligibility_status=INELIGIBLE,
        hard_eligibility_reason=shadow.structured_reason,
        action_status=action_status,
        review_kind="",
    )
    return replace(record, item=updated)


# 取得 audit item 的既有硬性狀態。
def _hard_status(record: AuditRecord) -> str:
    return record.item.hard_eligibility_status or record.item.eligibility_status


# 套用最終硬性狀態後重新計算可通知數。
def _is_notifiable(record: AuditRecord) -> bool:
    item = record.item
    return (
        item.notice_kind == APPLICATION
        and item.application_status not in _NON_ACTIONABLE_PERIODS
        and item.action_status in _ACTIONABLE_STATUSES
    )
