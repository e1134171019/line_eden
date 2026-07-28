# -*- coding: utf-8 -*-

from dataclasses import dataclass

from src.ai.gemini_requirement_extractor import GeminiRequirementExtraction
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    EligibilityDecision,
)
from src.profiles.student_profile import StudentProfile

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class ConditionCheck:
    """單一結構化必要條件的比對結果。"""

    field: str
    status: str
    reason: str


@dataclass(frozen=True)
class StructuredEligibilityResult:
    """結構化資格決策與所有可稽核條件。"""

    decision: EligibilityDecision
    checks: tuple[ConditionCheck, ...]


class StructuredEligibilityEvaluator:
    """只依 Gemini 結構化欄位與 profile 產生保守決策。"""

    def evaluate(
        self,
        extraction: GeminiRequirementExtraction,
        profile: StudentProfile,
    ) -> StructuredEligibilityResult:
        checks = self._build_checks(extraction, profile)
        failures = [item.reason for item in checks if item.status == FAIL]
        if failures:
            return StructuredEligibilityResult(
                EligibilityDecision(INELIGIBLE, tuple(dict.fromkeys(failures))),
                tuple(checks),
            )

        safety_unknowns = self._safety_unknowns(extraction)
        unknowns = [item.reason for item in checks if item.status == UNKNOWN]
        unknowns.extend(safety_unknowns)
        if unknowns:
            return StructuredEligibilityResult(
                EligibilityDecision(REVIEW, tuple(dict.fromkeys(unknowns))),
                tuple(checks),
            )

        passes = [item.reason for item in checks if item.status == PASS]
        if not _has_scope_evidence(checks):
            return StructuredEligibilityResult(
                EligibilityDecision(
                    REVIEW,
                    ("結構化條件未證明公告適用目前學制或背景，暫不推播。",),
                ),
                tuple(checks),
            )
        if not passes:
            return StructuredEligibilityResult(
                EligibilityDecision(REVIEW, ("未抽取可驗證的必要條件，暫不推播。",)),
                tuple(checks),
            )
        return StructuredEligibilityResult(
            EligibilityDecision(ELIGIBLE, tuple(dict.fromkeys(passes))),
            tuple(checks),
        )

    def _safety_unknowns(self, extraction: GeminiRequirementExtraction) -> list[str]:
        reasons: list[str] = []
        if extraction.document_type != "scholarship_rules":
            reasons.append("Gemini 未確認輸入是完整獎學金辦法。")
        if not extraction.criteria_complete:
            reasons.append("Gemini 判定資格條件不完整。")
        if extraction.needs_more_pages:
            reasons.append("Gemini 判定仍需要更多文件頁面。")
        if not extraction.evidence:
            reasons.append("Gemini 未提供可追溯的資格證據。")
        return reasons

    def _build_checks(
        self,
        extraction: GeminiRequirementExtraction,
        profile: StudentProfile,
    ) -> list[ConditionCheck]:
        checks: list[ConditionCheck] = []
        checks.extend(_check_applicant_groups(extraction, profile))
        checks.extend(_check_degree_levels(extraction, profile))
        checks.extend(_check_program_types(extraction, profile))
        checks.extend(_check_departments(extraction, profile))
        checks.extend(_check_special_statuses(extraction, profile))
        checks.extend(_check_scores(extraction, profile))
        checks.extend(_check_explicit_exclusions(extraction, profile))
        checks.extend(_unresolved_free_text_conditions(extraction))
        return checks


def _check_applicant_groups(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionCheck]:
    if not extraction.applicant_groups:
        return []
    combined = "、".join(extraction.applicant_groups)
    if _contains_any(combined, ("大專", "大學", "在校生", "學生")):
        return [ConditionCheck("applicant_groups", PASS, "申請對象包含大專或在校學生。")]
    if _contains_any(combined, ("研究生", "碩士", "博士")) and profile.degree_level == "學士":
        return [ConditionCheck("applicant_groups", FAIL, "公告申請對象限定研究所層級。")]
    return [ConditionCheck("applicant_groups", UNKNOWN, f"申請對象「{combined}」尚無法確定對應背景。")]


def _check_degree_levels(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionCheck]:
    levels = extraction.degree_levels
    if not levels:
        return []
    bachelor_allowed = any(_contains_any(item, ("大學生", "大學部", "學士", "大專")) for item in levels)
    graduate_allowed = any(_contains_any(item, ("研究生", "碩士", "博士")) for item in levels)
    if profile.degree_level == "學士" and not bachelor_allowed and graduate_allowed:
        return [ConditionCheck("degree_levels", FAIL, "公告限定研究所層級。")]
    if profile.degree_level == "學士" and bachelor_allowed:
        return [ConditionCheck("degree_levels", PASS, "公告學位層級包含學士生。")]
    return [ConditionCheck("degree_levels", UNKNOWN, "公告學位層級與 profile 無法直接比對。")]


def _check_program_types(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionCheck]:
    checks: list[ConditionCheck] = []
    for value in extraction.program_types_excluded:
        if _program_matches(value, profile):
            checks.append(ConditionCheck("program_types_excluded", FAIL, f"公告明確排除「{value}」。"))
    included = extraction.program_types_included
    if included:
        if any(_program_matches(value, profile) for value in included):
            checks.append(ConditionCheck("program_types_included", PASS, "公告包含目前進修或在職學制。"))
        else:
            joined = "、".join(included)
            checks.append(ConditionCheck("program_types_included", FAIL, f"公告限定學制「{joined}」，與目前學制不符。"))
    return checks


def _check_departments(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionCheck]:
    checks: list[ConditionCheck] = []
    for value in extraction.departments_excluded:
        if _department_matches(value, profile):
            checks.append(ConditionCheck("departments_excluded", FAIL, f"公告排除「{value}」相關科系。"))
    included = extraction.departments_included
    if included:
        if any(_department_matches(value, profile) for value in included):
            checks.append(ConditionCheck("departments_included", PASS, "公告指定科系與電子／電力背景相符。"))
        else:
            joined = "、".join(included)
            checks.append(ConditionCheck("departments_included", FAIL, f"公告限定科系「{joined}」，與目前科系不符。"))
    return checks


def _check_special_statuses(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionCheck]:
    required = [item for item in extraction.required_special_statuses if item.strip()]
    if not required:
        return []
    owned = set(profile.special_statuses)
    matched = [item for item in required if any(term in item or item in term for term in owned)]
    if len(required) == 1 and not matched:
        return [ConditionCheck("required_special_statuses", FAIL, f"公告限定「{required[0]}」身分。")]
    if matched:
        return [ConditionCheck("required_special_statuses", PASS, "profile 具有公告要求的特殊身分。")]
    return [
        ConditionCheck(
            "required_special_statuses",
            UNKNOWN,
            "多個特殊身分條件的 AND／OR 關係尚未結構化，需人工確認。",
        )
    ]


def _check_scores(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionCheck]:
    checks: list[ConditionCheck] = []
    average = extraction.minimum_average_grade
    if average is not None:
        if profile.average_grade <= 0:
            checks.append(ConditionCheck("minimum_average_grade", UNKNOWN, "profile 未填學業平均。"))
        elif profile.average_grade < average:
            checks.append(ConditionCheck("minimum_average_grade", FAIL, f"學業平均未達 {average:g} 分門檻。"))
        else:
            checks.append(ConditionCheck("minimum_average_grade", PASS, f"學業平均符合 {average:g} 分門檻。"))
    conduct = extraction.minimum_conduct_grade
    if conduct is not None:
        if profile.conduct_grade <= 0:
            checks.append(ConditionCheck("minimum_conduct_grade", UNKNOWN, "profile 未填操行成績。"))
        elif profile.conduct_grade < conduct:
            checks.append(ConditionCheck("minimum_conduct_grade", FAIL, f"操行成績未達 {conduct:g} 分門檻。"))
        else:
            checks.append(ConditionCheck("minimum_conduct_grade", PASS, f"操行成績符合 {conduct:g} 分門檻。"))
    return checks


def _check_explicit_exclusions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionCheck]:
    checks: list[ConditionCheck] = []
    for value in extraction.explicit_exclusions:
        if _program_matches(value, profile):
            checks.append(ConditionCheck("explicit_exclusions", FAIL, f"公告明確排除「{value}」。"))
    return checks


def _unresolved_free_text_conditions(
    extraction: GeminiRequirementExtraction,
) -> list[ConditionCheck]:
    checks: list[ConditionCheck] = []
    if extraction.year_requirements:
        checks.append(ConditionCheck("year_requirements", UNKNOWN, "年級條件仍是自由文字，尚未完成結構化比對。"))
    if extraction.rank_requirement:
        checks.append(ConditionCheck("rank_requirement", UNKNOWN, "排名條件仍是自由文字，尚未完成結構化比對。"))
    if extraction.residence_requirement:
        checks.append(ConditionCheck("residence_requirement", UNKNOWN, "戶籍條件仍是自由文字，尚未完成結構化比對。"))
    if extraction.other_required_conditions:
        checks.append(ConditionCheck("other_required_conditions", UNKNOWN, "公告含其他必要條件，尚未完成結構化比對。"))
    return checks


def _program_matches(value: str, profile: StudentProfile) -> bool:
    if "進修" in value and "進修" in profile.program_type:
        return True
    if "在職" in value and profile.employed:
        return True
    if "日間" in value and "日間" in profile.program_type:
        return True
    return value.strip() == profile.program_type.strip()


def _department_matches(value: str, profile: StudentProfile) -> bool:
    terms = {profile.department, *profile.research_keywords, "電子", "電機", "電力", "能源"}
    return any(term and (term in value or value in term) for term in terms)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _has_scope_evidence(checks: list[ConditionCheck]) -> bool:
    scope_fields = {
        "applicant_groups",
        "degree_levels",
        "program_types_included",
        "departments_included",
        "required_special_statuses",
    }
    return any(item.field in scope_fields and item.status == PASS for item in checks)
