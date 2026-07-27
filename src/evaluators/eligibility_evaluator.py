# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

from config import ATTACHMENT_TEXT_MARKER
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
from src.evaluators.special_status_aliases import find_alias_exclusions
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile

ELIGIBLE = "eligible"
REVIEW = "review"
INELIGIBLE = "ineligible"


# 正規化比較詞與數字間的空白，統一成績門檻句型。
def _normalize_rule_text(text: str) -> str:
    normalized = normalize_text(text)
    return re.sub(r"(不得低於|至少|須達|需達|達)\s+(?=\d)", r"\1", normalized)


# 附件已成功解析時，只移除「仍需參閱附件」這一項未知原因。
def _filter_resolved_attachment_unknowns(text: str, unknowns: list[str]) -> list[str]:
    if ATTACHMENT_TEXT_MARKER not in text:
        return unknowns
    return [reason for reason in unknowns if "參閱附件" not in reason]


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

    # 評估公告，明確不符時排除，條件未知時保留人工確認。
    def evaluate(
        self,
        scholarship: Scholarship,
        detail_text: str,
        profile: StudentProfile,
    ) -> EligibilityDecision:
        title = normalize_text(scholarship.title)
        text = _normalize_rule_text(f"{title}。{detail_text}")
        exclusions = self._find_exclusions(title, text, profile)
        if exclusions:
            return EligibilityDecision(INELIGIBLE, tuple(exclusions))
        unknowns = self._find_unknowns(text, profile)
        if unknowns:
            return EligibilityDecision(REVIEW, tuple(unknowns))
        matches = find_matches(text, profile)
        matches = filter_contextual_matches(matches, title, detail_text, profile)
        matches = filter_general_college_matches(matches, text)
        if matches:
            return EligibilityDecision(ELIGIBLE, tuple(matches))
        return EligibilityDecision(REVIEW, ("公告未提供足夠條件，暫不推播。",))

    # 合併既有規則、身分別名與畢業年級安全排除。
    def _find_exclusions(
        self,
        title: str,
        text: str,
        profile: StudentProfile,
    ) -> list[str]:
        exclusions = find_alias_exclusions(title, text, profile)
        exclusions.extend(find_graduation_exclusions(title, text, profile))
        exclusions.extend(find_exclusions(text, title, profile))
        return filter_missing_score_exclusions(exclusions, profile)

    # 合併附件、個人資料缺值與既有待確認原因。
    def _find_unknowns(self, text: str, profile: StudentProfile) -> list[str]:
        unknowns = find_unknowns(text, profile)
        unknowns = _filter_resolved_attachment_unknowns(text, unknowns)
        unknowns.extend(find_safety_unknowns(text, profile))
        return list(dict.fromkeys(unknowns))
