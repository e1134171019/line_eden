# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Literal

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
ConditionStatus = Literal["pass", "fail", "unknown"]


@dataclass(frozen=True)
class ConditionResult:
    """單一必要條件對學生背景的比對結果。"""

    field: str
    requirement: str
    status: ConditionStatus
    reason: str


@dataclass(frozen=True)
class StructuredEligibilityResult:
    """結構化資格總決策與逐條條件矩陣。"""

    decision: EligibilityDecision
    conditions: tuple[ConditionResult, ...]


class StructuredEligibilityEvaluator:
    """只依 Gemini 結構化欄位與 profile 進行確定性比對。"""

    def evaluate(
        self,
        extraction: GeminiRequirementExtraction,
        profile: StudentProfile,
    ) -> StructuredEligibilityResult:
        conditions = self._conditions(extraction, profile)
        failures = [item.reason for item in conditions if item.status == FAIL]
        if failures:
            return StructuredEligibilityResult(
                EligibilityDecision(INELIGIBLE, tuple(dict.fromkeys(failures))),
                tuple(conditions),
            )

        incomplete = (
            extraction.document_type != "scholarship_rules"
            or not extraction.criteria_complete
            or extraction.needs_more_pages
            or not extraction.evidence
        )
        unknowns = [item.reason for item in conditions if item.status == UNKNOWN]
        if incomplete:
            unknowns.insert(0, "Gemini 抽取的資格文件不完整或證據不足。")
        if unknowns:
            return StructuredEligibilityResult(
                EligibilityDecision(REVIEW, tuple(dict.fromkeys(unknowns))),
                tuple(conditions),
            )

        passes = [item.reason for item in conditions if item.status == PASS]
        if not passes:
            return StructuredEligibilityResult(
                EligibilityDecision(REVIEW, ("沒有足夠的結構化條件可證明符合。",)),
                tuple(conditions),
            )
        return StructuredEligibilityResult(
            EligibilityDecision(ELIGIBLE, tuple(dict.fromkeys(passes))),
            tuple(conditions),
        )

    def _conditions(
        self,
        extraction: GeminiRequirementExtraction,
        profile: StudentProfile,
    ) -> list[ConditionResult]:
        results: list[ConditionResult] = []
        results.extend(_program_conditions(extraction, profile))
        results.extend(_degree_conditions(extraction, profile))
        results.extend(_department_conditions(extraction, profile))
        results.extend(_special_status_conditions(extraction, profile))
        results.extend(_score_conditions(extraction, profile))
        results.extend(_residence_conditions(extraction, profile))
        results.extend(_free_text_conditions(extraction))
        return results


def _program_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionResult]:
    results: list[ConditionResult] = []
    current = profile.program_type
    for excluded in extraction.program_types_excluded:
        if _same_program(excluded, current) or ("在職" in excluded and profile.employed):
            results.append(ConditionResult("program", excluded, FAIL, f"公告排除「{excluded}」。"))
    if extraction.program_types_included:
        matched = any(_same_program(item, current) for item in extraction.program_types_included)
        results.append(
            ConditionResult(
                "program",
                "、".join(extraction.program_types_included),
                PASS if matched else FAIL,
                "公告包含目前學制。" if matched else "公告列出的學制不包含目前學制。",
            )
        )
    return results


def _degree_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionResult]:
    if not extraction.degree_levels:
        return []
    is_bachelor = profile.degree_level == "學士"
    includes_college = any(term in value for value in extraction.degree_levels for term in ("大學生", "大學部", "學士", "大專"))
    includes_graduate = any(term in value for value in extraction.degree_levels for term in ("研究生", "碩士", "博士"))
    matched = includes_college if is_bachelor else includes_graduate
    return [
        ConditionResult(
            "degree",
            "、".join(extraction.degree_levels),
            PASS if matched else FAIL,
            "學位層級符合公告。" if matched else "公告限定的學位層級與目前不符。",
        )
    ]


def _department_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionResult]:
    results: list[ConditionResult] = []
    for excluded in extraction.departments_excluded:
        if _department_matches(excluded, profile):
            results.append(ConditionResult("department", excluded, FAIL, f"公告排除「{excluded}」相關科系。"))
    if extraction.departments_included:
        matched = any(_department_matches(item, profile) for item in extraction.departments_included)
        results.append(
            ConditionResult(
                "department",
                "、".join(extraction.departments_included),
                PASS if matched else FAIL,
                "科系或研究領域符合公告。" if matched else "公告指定科系與目前背景不符。",
            )
        )
    return results


def _special_status_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionResult]:
    owned = set(profile.special_statuses)
    return [
        ConditionResult(
            "special_status",
            status,
            PASS if status in owned else FAIL,
            f"具備必要身分「{status}」。" if status in owned else f"缺少必要身分「{status}」。",
        )
        for status in extraction.required_special_statuses
    ]


def _score_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionResult]:
    results: list[ConditionResult] = []
    for field, minimum, actual, label in (
        ("average_grade", extraction.minimum_average_grade, profile.average_grade, "學業平均"),
        ("conduct_grade", extraction.minimum_conduct_grade, profile.conduct_grade, "操行成績"),
    ):
        if minimum is None:
            continue
        if actual <= 0:
            results.append(ConditionResult(field, f"{minimum:g}", UNKNOWN, f"profile 缺少{label}資料。"))
        elif actual < minimum:
            results.append(ConditionResult(field, f"{minimum:g}", FAIL, f"{label}未達 {minimum:g} 分。"))
        else:
            results.append(ConditionResult(field, f"{minimum:g}", PASS, f"{label}符合 {minimum:g} 分門檻。"))
    return results


def _residence_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionResult]:
    required = extraction.residence_requirement
    if not required:
        return []
    if not profile.residence:
        return [ConditionResult("residence", required, UNKNOWN, "profile 缺少戶籍資料。")]
    matched = _normalize_region(profile.residence) in _normalize_region(required)
    return [
        ConditionResult(
            "residence",
            required,
            PASS if matched else FAIL,
            "戶籍條件符合公告。" if matched else "戶籍條件與公告不符。",
        )
    ]


def _free_text_conditions(extraction: GeminiRequirementExtraction) -> list[ConditionResult]:
    results = [
        ConditionResult("explicit_exclusion", value, UNKNOWN, f"明確排除條件仍需人工確認：{value}")
        for value in extraction.explicit_exclusions
    ]
    results.extend(
        ConditionResult("other_required", value, UNKNOWN, f"其他必要條件仍需人工確認：{value}")
        for value in extraction.other_required_conditions
    )
    if extraction.rank_requirement:
        results.append(ConditionResult("rank", extraction.rank_requirement, UNKNOWN, "排名條件尚未結構化。"))
    if extraction.year_requirements:
        results.append(ConditionResult("year", "、".join(extraction.year_requirements), UNKNOWN, "年級條件尚未結構化。"))
    return results


def _same_program(required: str, current: str) -> bool:
    if "進修" in required and "進修" in current:
        return True
    if "日間" in required and "日間" in current:
        return True
    if "在職" in required and "在職" in current:
        return True
    return required == current


def _department_matches(required: str, profile: StudentProfile) -> bool:
    terms = set(profile.research_keywords) | {profile.department, "電子", "電機", "電力", "能源"}
    return any(term and term in required for term in terms)


def _normalize_region(value: str) -> str:
    return value.replace("臺", "台").replace(" ", "")
