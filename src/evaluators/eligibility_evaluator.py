# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

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
from src.models.evaluator_input import (
    GEMINI_RULE_PARTIAL_EXCLUSIONS,
    EvaluatorInput,
)
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


def _assemble_evaluation_text(evaluator_input: EvaluatorInput) -> str:
    """只為規則掃描組裝文字；分隔標題不承擔任何狀態語意。"""
    parts = [evaluator_input.body_text.strip()]
    parts.extend(
        f"--- 附件 {index} ---\n{text.strip()}"
        for index, text in enumerate(
            evaluator_input.resolved_attachment_texts,
            start=1,
        )
        if text.strip()
    )
    if evaluator_input.gemini_rule_text:
        parts.append(
            "--- Gemini 資格抽取 ---\n"
            f"{evaluator_input.gemini_rule_text.strip()}"
        )
    return "\n\n".join(part for part in parts if part)


def _coerce_evaluator_input(
    detail: str | EvaluatorInput,
    rules_status: str | None,
) -> EvaluatorInput:
    if isinstance(detail, EvaluatorInput):
        if rules_status is None or rules_status == detail.rules_status:
            return detail
        return EvaluatorInput(
            body_text=detail.body_text,
            resolved_attachment_texts=detail.resolved_attachment_texts,
            gemini_rule_text=detail.gemini_rule_text,
            rules_status=rules_status,
            gemini_rule_scope=detail.gemini_rule_scope,
        )
    return EvaluatorInput(
        body_text=detail,
        rules_status=rules_status or RULES_STATUS_UNKNOWN,
    )


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


def _trusted_unresolved_text(
    title: str,
    evaluator_input: EvaluatorInput,
) -> str:
    """未完整解析時，只信任標題與明確標示為部分排除的 Gemini 證據。"""
    if (
        evaluator_input.gemini_rule_scope != GEMINI_RULE_PARTIAL_EXCLUSIONS
        or not evaluator_input.gemini_rule_text
    ):
        return title
    return _normalize_rule_text(
        f"{title}。{evaluator_input.gemini_rule_text}"
    )


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
        detail: str | EvaluatorInput,
        profile: StudentProfile,
        *,
        rules_status: str | None = None,
    ) -> EligibilityDecision:
        evaluator_input = _coerce_evaluator_input(detail, rules_status)
        effective_rules_status = evaluator_input.rules_status
        detail_text = _assemble_evaluation_text(evaluator_input)
        title = _normalize_rule_text(scholarship.title)
        text = _normalize_rule_text(f"{title}。{detail_text}")
        exclusions = find_deadline_exclusions(scholarship, text)
        exclusions.extend(
            self._find_exclusions(
                title,
                text,
                evaluator_input,
                profile,
                effective_rules_status,
            )
        )
        exclusions = _deduplicate_reasons(exclusions)
        if exclusions:
            return EligibilityDecision(INELIGIBLE, tuple(exclusions))
        unknowns = self._find_unknowns(text, profile, effective_rules_status)
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
        evaluator_input: EvaluatorInput,
        profile: StudentProfile,
        rules_status: str | None,
    ) -> list[str]:
        trusted_text = (
            _trusted_unresolved_text(title, evaluator_input)
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
