# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile

ELIGIBLE = "eligible"
REVIEW = "review"
INELIGIBLE = "ineligible"

SPECIAL_STATUS_KEYWORDS = (
    "原住民",
    "低收入戶",
    "中低收入戶",
    "身心障礙",
    "癌友家庭子女",
    "單親家庭",
    "清寒",
)


@dataclass(frozen=True)
class EligibilityDecision:
    """單筆公告對指定學生背景的資格判斷結果。"""

    status: str
    reasons: tuple[str, ...]

    # 將多個原因整理成可保存與顯示的文字。
    def reason_text(self) -> str:
        return "；".join(self.reasons)


class EligibilityEvaluator:
    """以公告文字與學生背景進行保守的規則式資格判斷。"""

    # 評估公告，明確不符時直接排除，其餘依正向條件分類。
    def evaluate(
        self,
        scholarship: Scholarship,
        detail_text: str,
        profile: StudentProfile,
    ) -> EligibilityDecision:
        text = self._normalize(f"{scholarship.title} {detail_text}")
        exclusions = self._find_exclusions(text, scholarship.title, profile)
        if exclusions:
            return EligibilityDecision(INELIGIBLE, tuple(exclusions))
        matches = self._find_matches(text, profile)
        if matches:
            return EligibilityDecision(ELIGIBLE, tuple(matches))
        return EligibilityDecision(REVIEW, ("公告未提供足夠條件，暫不推播。",))

    # 收集學制、年級、身分與成績的明確不符合條件。
    def _find_exclusions(
        self,
        text: str,
        title: str,
        profile: StudentProfile,
    ) -> list[str]:
        reasons: list[str] = []
        reasons.extend(self._check_program(text, profile))
        reasons.extend(self._check_degree_and_year(text, profile))
        reasons.extend(self._check_special_status(text, title, profile))
        reasons.extend(self._check_grade_thresholds(text, profile))
        return reasons

    # 判斷日間部、進修部或在職身分的明確限制。
    def _check_program(self, text: str, profile: StudentProfile) -> list[str]:
        reasons: list[str] = []
        if "日間部" in text and "日間" not in profile.program_type:
            reasons.append("公告限定日間部，與目前學制不符。")
        if re.search(r"不(?:含|受理|接受).{0,6}進修部", text) and "進修" in profile.program_type:
            reasons.append("公告明確排除進修部。")
        if re.search(r"不(?:含|受理|接受).{0,6}在職", text) and profile.employed:
            reasons.append("公告明確排除在職學生。")
        return reasons

    # 判斷學位層級、新生或應屆畢業年級限制。
    def _check_degree_and_year(self, text: str, profile: StudentProfile) -> list[str]:
        reasons: list[str] = []
        graduate_terms = ("研究生", "碩士班", "博士班", "碩博士")
        if any(term in text for term in graduate_terms) and profile.degree_level == "學士":
            reasons.append("公告限定研究所層級。")
        if any(term in text for term in ("高中生", "高職生", "國中生", "國小生")):
            reasons.append("公告限定非大專學制。")
        if re.search(r"(?:限|僅限).{0,4}(?:新生|大一)", text) and profile.year > 1:
            reasons.append("公告限定新生或大一學生。")
        if "應屆畢業" in text and profile.year < 4:
            reasons.append("公告限定應屆畢業生。")
        return reasons

    # 判斷特定家庭或法定身分限制。
    def _check_special_status(
        self,
        text: str,
        title: str,
        profile: StudentProfile,
    ) -> list[str]:
        profile_statuses = set(profile.special_statuses)
        for keyword in SPECIAL_STATUS_KEYWORDS:
            required = keyword in title or re.search(
                rf"(?:限|僅限|須|需|具有|具備|對象為).{{0,12}}{keyword}",
                text,
            )
            if required and keyword not in profile_statuses:
                return [f"公告限定「{keyword}」身分。"]
        return []

    # 判斷學業與操行成績門檻。
    def _check_grade_thresholds(
        self,
        text: str,
        profile: StudentProfile,
    ) -> list[str]:
        reasons: list[str] = []
        average = self._extract_threshold(text, ("學業平均", "平均成績", "學業成績"))
        conduct = self._extract_threshold(text, ("操行成績", "操行"))
        if average is not None and profile.average_grade < average:
            reasons.append(f"學業平均未達 {average:g} 分門檻。")
        if conduct is not None and profile.conduct_grade < conduct:
            reasons.append(f"操行成績未達 {conduct:g} 分門檻。")
        return reasons

    # 收集可確認符合的學校、科系、成績或一般大專資格。
    def _find_matches(self, text: str, profile: StudentProfile) -> list[str]:
        reasons: list[str] = []
        if profile.school and profile.school in text:
            reasons.append("公告適用學校與目前就讀學校相符。")
        if profile.department and profile.department in text:
            reasons.append("公告指定科系與目前科系相符。")
        keywords = set(profile.research_keywords) | {"電子", "電機", "電力", "能源"}
        if any(keyword and keyword in text for keyword in keywords):
            reasons.append("公告領域與電子／電力相關背景相符。")
        if "優秀學生" in text and profile.average_grade >= 80:
            reasons.append("學業成績符合優秀學生型獎學金的基本方向。")
        if any(term in text for term in ("大專院校學生", "大學生", "在校生")):
            reasons.append("公告適用一般大專在校生，未發現明確排除條件。")
        return reasons

    # 從公告文字中擷取指定成績欄位的最低分數。
    def _extract_threshold(self, text: str, labels: tuple[str, ...]) -> float | None:
        label_pattern = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"(?:{label_pattern}).{{0,12}}?(\d{{2,3}})(?:\.\d+)?\s*分?以上", text)
        return float(match.group(1)) if match else None

    # 壓縮公告空白，避免換行影響關鍵字判斷。
    def _normalize(self, text: str) -> str:
        return " ".join(text.split())
