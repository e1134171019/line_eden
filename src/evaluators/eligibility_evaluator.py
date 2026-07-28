# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

from config import GEMINI_PARTIAL_EXCLUSION_MARKER
from src.diagnostics.detail_fetch_diagnostics import (
    RULES_STATUS_DECLARED_MISSING,
    RULES_STATUS_DISCOVERED_UNRESOLVED,
    RULES_STATUS_GENERIC_UNCONFIRMED,
    RULES_STATUS_NOT_REQUIRED,
    RULES_STATUS_RESOLVED,
    RULES_STATUS_UNKNOWN,
)
from src.evaluators.eligibility_completeness import (
    find_completeness_unknowns,
    find_hard_exclusions,
    normalize_eligibility_text,
)
from src.evaluators.eligibility_rules import (
    find_exclusions,
    find_matches,
    find_unknowns,
    normalize_text,
)
from src.evaluators.eligibility_safety_rules import (
    filter_general_college_matches,
    filter_missing_score_exclusions,
    find_graduation_exclusions,
    find_safety_unknowns,
)
from src.evaluators.match_context import filter_contextual_matches
from src.evaluators.runtime_safety import find_deadline_exclusions, find_runtime_unknowns
from src.evaluators.special_status_aliases import find_alias_exclusions
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile

ELIGIBLE = "eligible"
REVIEW = "review"
INELIGIBLE = "ineligible"

_SAFE_RULES_STATUSES = {
    RULES_STATUS_NOT_REQUIRED,
    RULES_STATUS_RESOLVED,
}


def _normalize_rule_text(text: str) -> str:
    normalized = normalize_eligibility_text(normalize_text(text))
    return re.sub(r"(不得低於|至少|須達|需達|達)\s+(?=\d)", r"\1", normalized)


def _filter_resolved_attachment_unknowns(
    unknowns: list[str],
    rules_status: str | None,
) -> list[str]:
    """只有結構化狀態確認主要辦法已解析時才解除附件 unknown。"""
    if rules_status != RULES_STATUS_RESOLVED:
        return unknowns
    return [reason for reason in unknowns if "參閱附件" not in reason]


def _rules_status_unknown_reason(rules_status: str | None) -> str | None:
    if rules_status in (None, RULES_STATUS_UNKNOWN) or rules_status in _SAFE_RULES_STATUSES:
        return None
    if rules_status == RULES_STATUS_DECLARED_MISSING:
        return "公告明示資格位於附件，但未找到附件連結，暫不推播。"
    if rules_status == RULES_STATUS_GENERIC_UNCONFIRMED:
        return "已找到通用附件，但尚未確認其為主要資格辦法，暫不推播。"
    if rules_status == RULES_STATUS_DISCOVERED_UNRESOLVED:
        return "主要資格辦法尚未成功解析，資格無法完整確認。"
    return "主要資格證據狀態不完整，暫不推播。"


def _rules_status_is_unresolved(rules_status: str | None) -> bool:
    return rules_status not in (None, RULES_STATUS_UNKNOWN, *_SAFE_RULES_STATUSES)


def _deduplicate_reasons(reasons: list[str]) -> list[str]:
    unique = list(dict.fromkeys(reasons))
    graduate_detailed = "公告限定研究所或博士生層級。"
    graduate_generic = "公告限定研究所層級。"
    if graduate_detailed in unique and graduate_generic in unique:
        unique.remove(graduate_generic)
    program_detailed = "公告明確排除進修部或進修推廣學制。"
    program_generic = "公告明確排除進修部。"
    if program_detailed in unique and program_generic in unique:
        unique.remove(program_generic)
    return unique


def _trusted_unresolved_text(title: str, detail_text: str) -> str:
    if GEMINI_PARTIAL_EXCLUSION_MARKER not in detail_text:
        return title
    partial = detail_text.split(GEMINI_PARTIAL_EXCLUSION_MARKER, 1)[1]
    return _normalize_rule_text(f"{title}。{partial}")


@dataclass(frozen=True)
class EligibilityDecision:
    """單筆公告對指定學生背景的資格判斷結果。"""

    status: str
    reasons: tuple[str, ...]

    def reason_text(self) -> str:
        return "；".join(self.reasons)


class EligibilityEvaluator:
    """協調資格規則並產生保守的適合度判斷。"""

    def evaluate(
        self,
        scholarship: Scholarship,
        detail_text: str,
        profile: StudentProfile,
        *,
        rules_status: str | None = None,
    ) -> EligibilityDecision:
        title = _normalize_rule_text(scholarship.title)
        text = _normalize_rule_text(f"{title}。{detail_text}")
        exclusions = find_deadline_exclusions(scholarship, text)
        exclusions.extend(
            self._find_exclusions(
                title,
                text,
                detail_text,
                profile,
                rules_status,
            )
        )
        exclusions = _deduplicate_reasons(exclusions)
        if exclusions:
            return EligibilityDecision(INELIGIBLE, tuple(exclusions))
        unknowns = self._find_unknowns(text, profile, rules_status)
        if unknowns:
            return EligibilityDecision(REVIEW, tuple(unknowns))
        matches = find_matches(text, profile)
        matches = filter_contextual_matches(matches, title, detail_text, profile)
        matches = filter_general_college_matches(matches, text)
        completeness = find_completeness_unknowns(matches)
        if completeness:
            return EligibilityDecision(REVIEW, tuple(completeness))
        if matches:
            return EligibilityDecision(ELIGIBLE, tuple(dict.fromkeys(matches)))
        return EligibilityDecision(REVIEW, ("公告未提供足夠條件，暫不推播。",))

    def _find_exclusions(
        self,
        title: str,
        text: str,
        detail_text: str,
        profile: StudentProfile,
        rules_status: str | None,
    ) -> list[str]:
        trusted_text = (
            _trusted_unresolved_text(title, detail_text)
            if _rules_status_is_unresolved(rules_status)
            else text
        )
        exclusions = find_hard_exclusions(title, trusted_text, profile)
        exclusions.extend(find_alias_exclusions(title, trusted_text, profile))
        exclusions.extend(find_graduation_exclusions(title, trusted_text, profile))
        exclusions.extend(find_exclusions(trusted_text, title, profile))
        filtered = filter_missing_score_exclusions(exclusions, profile)
        return _deduplicate_reasons(filtered)

    def _find_unknowns(
        self,
        text: str,
        profile: StudentProfile,
        rules_status: str | None,
    ) -> list[str]:
        unknowns = find_unknowns(text, profile)
        unknowns = _filter_resolved_attachment_unknowns(unknowns, rules_status)
        status_reason = _rules_status_unknown_reason(rules_status)
        if status_reason:
            unknowns.append(status_reason)
        unknowns.extend(find_runtime_unknowns(text, profile))
        unknowns.extend(find_safety_unknowns(text, profile))
        return list(dict.fromkeys(unknowns))
