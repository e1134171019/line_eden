# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

from src.evaluators.eligibility_rules import (
    find_exclusions,
    find_matches,
    find_unknowns,
    normalize_text,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile

ELIGIBLE = "eligible"
REVIEW = "review"
INELIGIBLE = "ineligible"


# 正規化比較詞與數字間的空白，統一成績門檻句型。
def _normalize_rule_text(text: str) -> str:
    normalized = normalize_text(text)
    return re.sub(r"(不得低於|至少|須達|需達|達)\s+(?=\d)", r"\1", normalized)


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
        exclusions = find_exclusions(text, title, profile)
        if exclusions:
            return EligibilityDecision(INELIGIBLE, tuple(exclusions))
        unknowns = find_unknowns(text, profile)
        if unknowns:
            return EligibilityDecision(REVIEW, tuple(unknowns))
        matches = find_matches(text, profile)
        if matches:
            return EligibilityDecision(ELIGIBLE, tuple(matches))
        return EligibilityDecision(REVIEW, ("公告未提供足夠條件，暫不推播。",))
