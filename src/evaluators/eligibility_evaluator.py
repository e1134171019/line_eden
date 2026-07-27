# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

from config import (
    ATTACHMENT_TEXT_MARKER,
    GEMINI_PARTIAL_EXCLUSION_MARKER,
    UNRESOLVED_ATTACHMENT_MARKER,
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


# 正規化比較詞、括號身分與數字間空白，統一資格句型。
def _normalize_rule_text(text: str) -> str:
    normalized = normalize_eligibility_text(normalize_text(text))
    return re.sub(r"(不得低於|至少|須達|需達|達)\s+(?=\d)", r"\1", normalized)


# 附件已成功解析時，只移除「仍需參閱附件」這一項未知原因。
def _filter_resolved_attachment_unknowns(text: str, unknowns: list[str]) -> list[str]:
    if ATTACHMENT_TEXT_MARKER not in text:
        return unknowns
    return [reason for reason in unknowns if "參閱附件" not in reason]


# 合併語意相同的排除原因，保留資訊較完整的一句。
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


# 主要附件未解析時，只加入 Gemini 有證據的部分硬性排除文字。
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

    # 將多個原因整理成可保存與顯示的文字。
    def reason_text(self) -> str:
        return "；".join(self.reasons)


class EligibilityEvaluator:
    """協調資格規則並產生保守的適合度判斷。"""

    # 評估公告，先排除過期與硬性不符，再確認未知與適用對象完整性。
    def evaluate(
        self,
        scholarship: Scholarship,
        detail_text: str,
        profile: StudentProfile,
    ) -> EligibilityDecision:
        title = _normalize_rule_text(scholarship.title)
        text = _normalize_rule_text(f"{title}。{detail_text}")
        exclusions = find_deadline_exclusions(scholarship, text)
        exclusions.extend(self._find_exclusions(title, text, detail_text, profile))
        exclusions = _deduplicate_reasons(exclusions)
        if exclusions:
            return EligibilityDecision(INELIGIBLE, tuple(exclusions))
        unknowns = self._find_unknowns(text, profile)
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

    # 主要辦法未解析時，正文雜訊不得產生硬性排除；只信任標題及 Gemini 證據。
    def _find_exclusions(
        self,
        title: str,
        text: str,
        detail_text: str,
        profile: StudentProfile,
    ) -> list[str]:
        trusted_text = (
            _trusted_unresolved_text(title, detail_text)
            if UNRESOLVED_ATTACHMENT_MARKER in detail_text
            else text
        )
        exclusions = find_hard_exclusions(title, trusted_text, profile)
        exclusions.extend(find_alias_exclusions(title, trusted_text, profile))
        exclusions.extend(find_graduation_exclusions(title, trusted_text, profile))
        exclusions.extend(find_exclusions(trusted_text, title, profile))
        filtered = filter_missing_score_exclusions(exclusions, profile)
        return _deduplicate_reasons(filtered)

    # 合併附件、全職學生、個人資料缺值與既有待確認原因。
    def _find_unknowns(self, text: str, profile: StudentProfile) -> list[str]:
        unknowns = find_unknowns(text, profile)
        unknowns = _filter_resolved_attachment_unknowns(text, unknowns)
        unknowns.extend(find_runtime_unknowns(text, profile))
        unknowns.extend(find_safety_unknowns(text, profile))
        return list(dict.fromkeys(unknowns))
