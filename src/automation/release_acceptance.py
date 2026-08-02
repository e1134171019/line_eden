# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Any

from src.evaluators.eligibility_evaluator import ELIGIBLE, INELIGIBLE
from src.services.scholarship_service import AuditRecord, AuditResult

EXPECTED_PROGRAM_COUNT = 38
REQUIRED_PROGRAM_IDS = frozenset({"auden-university-talent", "songliang-aid"})
ACCEPTED_PROGRAM_STATUSES = frozenset(
    {"matched", "no_current_announcement", "expired_known"}
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
        *_songliang_failures(audit_result.records),
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


def _songliang_failures(records: list[AuditRecord]) -> tuple[str, ...]:
    songliang = [record for record in records if record.item.program_id == "songliang-aid"]
    if not songliang:
        return ("松樑未進入 production 稽核結果",)
    statuses = {_hard_status(record) for record in songliang}
    if statuses == {INELIGIBLE}:
        return tuple()
    return ("松樑最終狀態必須為 ineligible，實際為 " + ", ".join(sorted(statuses)),)


def _hard_conflict_failures(records: list[AuditRecord]) -> tuple[str, ...]:
    failures = []
    for record in records:
        shadow = record.structured_shadow
        if shadow is None:
            continue
        statuses = {shadow.legacy_status, shadow.structured_status}
        if statuses != {ELIGIBLE, INELIGIBLE}:
            continue
        identifier = record.item.program_id or record.item.title
        failures.append(
            f"{identifier} evaluator 硬衝突："
            f"legacy={shadow.legacy_status}, structured={shadow.structured_status}"
        )
    return tuple(failures)


def _hard_status(record: AuditRecord) -> str:
    return record.item.hard_eligibility_status or record.item.eligibility_status
