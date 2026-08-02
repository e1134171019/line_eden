# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Any

from src.catalogs.tun_2025_program_catalog import TUN_2025_PROGRAMS
from src.evaluators.application_evidence_scorer import VALID_APPLICATION_DETAIL
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    REVIEW_SOURCE_INCOMPLETE,
)
from src.evaluators.notice_classifier import APPLICATION
from src.evaluators.runtime_safety import (
    DEADLINE_UNKNOWN,
    EVERGREEN,
    OPEN,
    UPCOMING,
)
from src.matchers.program_name_matcher import match_programs
from src.models.eligibility_axes import APPLY_CANDIDATE
from src.services.scholarship_service import AuditRecord, AuditResult

EXPECTED_PROGRAM_COUNT = 38
AUDEN_PROGRAM_ID = "auden-university-talent"
SONGLIANG_PROGRAM_ID = "songliang-aid"
REQUIRED_PROGRAM_IDS = frozenset({AUDEN_PROGRAM_ID, SONGLIANG_PROGRAM_ID})
ACCEPTED_PROGRAM_STATUSES = frozenset(
    {"matched", "no_current_announcement", "expired_known"}
)
ACTIONABLE_APPLICATION_STATUSES = frozenset(
    {OPEN, UPCOMING, EVERGREEN, DEADLINE_UNKNOWN}
)


@dataclass(frozen=True)
class ReleaseAcceptance:
    """合併與 LINE 前的 production 驗收結果。"""

    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures

    def require_passed(self) -> None:
        if self.failures:
            raise RuntimeError("Production 驗收未通過：" + "；".join(self.failures))


def evaluate_release_acceptance(
    source_report: dict[str, Any],
    audit_result: AuditResult,
) -> ReleaseAcceptance:
    program_states = _program_states(source_report)
    failures = [
        *_program_count_failures(program_states),
        *_required_program_failures(program_states),
        *_source_status_failures(program_states),
        *_auden_failures(audit_result.records),
        *_songliang_failures(audit_result.records),
        *_actionable_source_incomplete_failures(audit_result.records),
        *_hard_conflict_failures(audit_result.records),
    ]
    return ReleaseAcceptance(tuple(failures))


def _program_states(source_report: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    raw = source_report.get("program_states", [])
    if not isinstance(raw, list):
        return tuple()
    return tuple(item for item in raw if isinstance(item, dict))


def _program_count_failures(states: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    if len(states) == EXPECTED_PROGRAM_COUNT:
        return tuple()
    return (f"逐方案來源結果應為 38 項，實際為 {len(states)} 項",)


def _required_program_failures(states: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    program_ids = {str(item.get("program_id", "")) for item in states}
    missing = sorted(REQUIRED_PROGRAM_IDS - program_ids)
    if not missing:
        return tuple()
    return ("必要方案未出現在逐方案結果：" + ", ".join(missing),)


def _source_status_failures(states: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    failures = []
    for item in states:
        status = str(item.get("status", ""))
        if status in ACCEPTED_PROGRAM_STATUSES:
            continue
        program_id = str(item.get("program_id", "unknown"))
        failures.append(f"{program_id} 來源狀態為 {status or 'unknown'}")
    return tuple(failures)


def _auden_failures(records: list[AuditRecord]) -> tuple[str, ...]:
    auden = [
        record
        for record in records
        if record.item.program_id == AUDEN_PROGRAM_ID
        and record.item.notice_kind == APPLICATION
        and record.item.application_status in ACTIONABLE_APPLICATION_STATUSES
        and record.item.resolution_status == VALID_APPLICATION_DETAIL
    ]
    if not auden:
        return ("耀登優秀人才沒有可驗證的當期完整申請公告",)

    eligible = [
        record
        for record in auden
        if _hard_status(record) == ELIGIBLE
        and record.item.action_status == APPLY_CANDIDATE
    ]
    if eligible:
        return tuple()

    statuses = sorted({_hard_status(record) for record in auden})
    reasons = sorted(
        {
            record.item.hard_eligibility_reason or record.item.eligibility_reason
            for record in auden
            if record.item.hard_eligibility_reason or record.item.eligibility_reason
        }
    )
    detail = "｜".join(reasons) if reasons else "無原因"
    return (
        "耀登優秀人才必須產生 eligible + apply_candidate，實際為 "
        + ", ".join(statuses)
        + f"（{detail}）",
    )


def _songliang_failures(records: list[AuditRecord]) -> tuple[str, ...]:
    songliang = [
        record for record in records if record.item.program_id == SONGLIANG_PROGRAM_ID
    ]
    if not songliang:
        return ("松樑未進入 production 稽核結果",)

    authoritative = [
        record
        for record in songliang
        if record.item.resolution_status == VALID_APPLICATION_DETAIL
    ]
    failures: list[str] = []
    if not authoritative:
        failures.append("松樑沒有可驗證的正式辦法或完整申請正文")
    elif not any(_hard_status(record) == INELIGIBLE for record in authoritative):
        statuses = sorted({_hard_status(record) for record in authoritative})
        failures.append(
            "松樑正式辦法必須判定為 ineligible，實際為 "
            + ", ".join(statuses)
        )

    false_positive = [
        record
        for record in songliang
        if record.item.notice_kind == APPLICATION
        and _hard_status(record) == ELIGIBLE
    ]
    if false_positive:
        failures.append("松樑仍有 application 記錄被判定為 eligible")
    if any(record.item.action_status == APPLY_CANDIDATE for record in songliang):
        failures.append("松樑仍被列為可準備申請")
    return tuple(failures)


def _actionable_source_incomplete_failures(
    records: list[AuditRecord],
) -> tuple[str, ...]:
    resolved_programs = _resolved_actionable_programs(records)
    unresolved: dict[str, None] = {}
    for record in records:
        item = record.item
        if item.notice_kind != APPLICATION:
            continue
        if item.application_status not in ACTIONABLE_APPLICATION_STATUSES:
            continue
        if _hard_status(record) != REVIEW:
            continue
        source_incomplete = (
            item.review_kind == REVIEW_SOURCE_INCOMPLETE
            or item.resolution_status != VALID_APPLICATION_DETAIL
        )
        if not source_incomplete:
            continue
        identifier = _canonical_program_identifier(record)
        if identifier in resolved_programs:
            continue
        unresolved.setdefault(identifier, None)
    if not unresolved:
        return tuple()
    identifiers = ", ".join(unresolved)
    return (
        f"仍有 {len(unresolved)} 筆可行動公告來源不完整：{identifiers}",
    )


def _resolved_actionable_programs(records: list[AuditRecord]) -> frozenset[str]:
    resolved: set[str] = set()
    for record in records:
        item = record.item
        if item.notice_kind != APPLICATION:
            continue
        if item.application_status not in ACTIONABLE_APPLICATION_STATUSES:
            continue
        if item.resolution_status != VALID_APPLICATION_DETAIL:
            continue
        if (
            _hard_status(record) == REVIEW
            and item.review_kind == REVIEW_SOURCE_INCOMPLETE
        ):
            continue
        resolved.add(_canonical_program_identifier(record))
    return frozenset(resolved)


def _canonical_program_identifier(record: AuditRecord) -> str:
    item = record.item
    if item.program_id:
        return item.program_id
    match = match_programs(item.title, TUN_2025_PROGRAMS)
    if match.matched and match.program_id:
        return match.program_id
    return item.title


def _hard_conflict_failures(records: list[AuditRecord]) -> tuple[str, ...]:
    failures = []
    for record in records:
        shadow = record.structured_shadow
        if shadow is None:
            continue
        statuses = {shadow.legacy_status, shadow.structured_status}
        if statuses != {ELIGIBLE, INELIGIBLE}:
            continue
        if _hard_status(record) == INELIGIBLE:
            continue
        identifier = record.item.program_id or record.item.title
        failures.append(
            f"{identifier} evaluator 硬衝突未由 ineligible veto 解決："
            f"legacy={shadow.legacy_status}, structured={shadow.structured_status}"
        )
    return tuple(failures)


def _hard_status(record: AuditRecord) -> str:
    return record.item.hard_eligibility_status or record.item.eligibility_status
