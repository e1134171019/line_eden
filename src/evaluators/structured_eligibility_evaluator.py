# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re
from typing import Literal

from src.ai.gemini_requirement_extractor import GeminiRequirementExtraction
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    REVIEW_PROFILE_MISSING,
    REVIEW_SEMANTIC_AMBIGUOUS,
    REVIEW_SOURCE_INCOMPLETE,
    EligibilityDecision,
)
from src.evaluators.manual_check_extractor import extract_manual_checks
from src.profiles.student_profile import StudentProfile

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"
MANUAL = "manual"
ConditionStatus = Literal["pass", "fail", "unknown", "manual"]

_PROFILE_SPECIAL_STATUS_MARKERS = (
    "低收入",
    "中低收入",
    "清寒",
    "弱勢",
    "原住民",
    "身心障礙",
    "新住民",
    "單親",
    "特殊境遇",
    "失親",
    "孤兒",
    "隔代教養",
    "育幼",
    "燒傷",
    "心臟病",
    "罕見疾病",
    "重大傷病",
    "勞工子女",
    "農漁民",
    "遺族",
    "受刑人子女",
)


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
    """依結構化硬性欄位比對；成績與排名只列人工確認。"""

    def evaluate(
        self,
        extraction: GeminiRequirementExtraction,
        profile: StudentProfile,
    ) -> StructuredEligibilityResult:
        conditions = self._conditions(extraction, profile)
        manual_checks = tuple(
            dict.fromkeys(item.reason for item in conditions if item.status == MANUAL)
        )
        failures = [item.reason for item in conditions if item.status == FAIL]
        if failures:
            return StructuredEligibilityResult(
                EligibilityDecision(
                    INELIGIBLE,
                    tuple(dict.fromkeys(failures)),
                    manual_checks,
                ),
                tuple(conditions),
            )

        unknowns = [item.reason for item in conditions if item.status == UNKNOWN]
        if unknowns:
            unique = tuple(dict.fromkeys(unknowns))
            return StructuredEligibilityResult(
                EligibilityDecision(
                    REVIEW,
                    unique,
                    manual_checks,
                    _review_kind(unique),
                ),
                tuple(conditions),
            )

        incomplete = (
            extraction.document_type != "scholarship_rules"
            or not extraction.criteria_complete
            or extraction.needs_more_pages
            or not extraction.evidence
        )
        if incomplete:
            reason = "Gemini 抽取的資格文件不完整或證據不足。"
            return StructuredEligibilityResult(
                EligibilityDecision(
                    REVIEW,
                    (reason,),
                    manual_checks,
                    REVIEW_SOURCE_INCOMPLETE,
                ),
                tuple(conditions),
            )

        passes = [item.reason for item in conditions if item.status == PASS]
        if not passes:
            return StructuredEligibilityResult(
                EligibilityDecision(
                    REVIEW,
                    ("沒有足夠的結構化硬性條件可證明適用對象。",),
                    manual_checks,
                    REVIEW_SOURCE_INCOMPLETE,
                ),
                tuple(conditions),
            )
        return StructuredEligibilityResult(
            EligibilityDecision(
                ELIGIBLE,
                tuple(dict.fromkeys(passes)),
                manual_checks,
            ),
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
        results.extend(_score_conditions(extraction))
        results.extend(_residence_conditions(extraction, profile))
        results.extend(_year_conditions(extraction, profile))
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
            results.append(
                ConditionResult("program", excluded, FAIL, f"公告排除「{excluded}」。")
            )
    if extraction.program_types_included:
        matched = any(
            _same_program(item, current) for item in extraction.program_types_included
        )
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
    includes_college = any(
        term in value
        for value in extraction.degree_levels
        for term in ("大學生", "大學部", "學士", "大專")
    )
    includes_graduate = any(
        term in value
        for value in extraction.degree_levels
        for term in ("研究生", "碩士", "博士")
    )
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
            results.append(
                ConditionResult(
                    "department",
                    excluded,
                    FAIL,
                    f"公告排除「{excluded}」相關科系。",
                )
            )
    if extraction.departments_included:
        matched = any(
            _department_matches(item, profile)
            for item in extraction.departments_included
        )
        results.append(
            ConditionResult(
                "department",
                "、".join(extraction.departments_included),
                PASS if matched else FAIL,
                "科系或研究領域符合公告。"
                if matched
                else "公告指定科系與目前背景不符。",
            )
        )
    return results


def _special_status_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionResult]:
    required = tuple(dict.fromkeys(extraction.required_special_statuses))
    if not required:
        return []

    profile_statuses = tuple(
        status for status in required if _is_profile_special_status(status)
    )
    qualitative_requirements = tuple(
        status for status in required if status not in profile_statuses
    )
    results = [
        ConditionResult(
            "qualitative_requirement",
            value,
            MANUAL,
            f"請自行確認：是否符合「{value}」評選條件。",
        )
        for value in qualitative_requirements
    ]
    if not profile_statuses:
        return results

    matched = next(
        (
            owned
            for required_status in profile_statuses
            for owned in profile.special_statuses
            if _special_status_matches(required_status, owned)
        ),
        "",
    )
    requirement = "、".join(profile_statuses)
    if matched:
        results.append(
            ConditionResult(
                "special_status_any_of",
                requirement,
                PASS,
                f"具備必要身分選項之一：「{matched}」。",
            )
        )
    else:
        results.append(
            ConditionResult(
                "special_status_any_of",
                requirement,
                FAIL,
                f"須具備以下任一身分：{requirement}。",
            )
        )
    return results


def _score_conditions(
    extraction: GeminiRequirementExtraction,
) -> list[ConditionResult]:
    results: list[ConditionResult] = []
    for field, minimum, label in (
        ("average_grade", extraction.minimum_average_grade, "學業平均"),
        ("conduct_grade", extraction.minimum_conduct_grade, "操行成績"),
    ):
        if minimum is None:
            continue
        results.append(
            ConditionResult(
                field,
                f"{minimum:g}",
                MANUAL,
                f"請自行確認：{label}須達 {minimum:g} 分門檻。",
            )
        )
    if extraction.rank_requirement:
        results.append(
            ConditionResult(
                "rank",
                extraction.rank_requirement,
                MANUAL,
                f"請自行確認：{extraction.rank_requirement}。",
            )
        )
    return results


def _residence_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionResult]:
    required = extraction.residence_requirement
    if not required:
        return []
    if not profile.residence:
        return [
            ConditionResult(
                "residence",
                required,
                UNKNOWN,
                "profile 缺少戶籍資料。",
            )
        ]
    matched = _normalize_region(profile.residence) in _normalize_region(required)
    return [
        ConditionResult(
            "residence",
            required,
            PASS if matched else FAIL,
            "戶籍條件符合公告。" if matched else "戶籍條件與公告不符。",
        )
    ]


def _year_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[ConditionResult]:
    if not extraction.year_requirements:
        return []
    requirement = "、".join(extraction.year_requirements)
    years = _extract_years(requirement)
    if not years:
        return [
            ConditionResult(
                "year",
                requirement,
                UNKNOWN,
                f"年級條件語意仍需人工確認：{requirement}",
            )
        ]
    matched = profile.year in years
    return [
        ConditionResult(
            "year",
            requirement,
            PASS if matched else FAIL,
            "年級條件符合公告。" if matched else "目前年級不在公告允許範圍。",
        )
    ]


def _free_text_conditions(
    extraction: GeminiRequirementExtraction,
) -> list[ConditionResult]:
    results = [
        ConditionResult(
            "explicit_exclusion",
            value,
            UNKNOWN,
            f"明確排除條件仍需人工確認：{value}",
        )
        for value in extraction.explicit_exclusions
    ]
    for value in extraction.other_required_conditions:
        manual_checks = extract_manual_checks(value)
        if manual_checks:
            results.extend(
                ConditionResult("other_manual", value, MANUAL, check)
                for check in manual_checks
            )
        else:
            results.append(
                ConditionResult(
                    "other_required",
                    value,
                    UNKNOWN,
                    f"其他必要條件仍需人工確認：{value}",
                )
            )
    return results


def _review_kind(reasons: tuple[str, ...]) -> str:
    text = "｜".join(reasons)
    if any(marker in text for marker in ("不完整", "證據", "辦法", "附件")):
        return REVIEW_SOURCE_INCOMPLETE
    if any(marker in text for marker in ("profile", "缺少")):
        return REVIEW_PROFILE_MISSING
    return REVIEW_SEMANTIC_AMBIGUOUS


def _extract_years(value: str) -> set[int]:
    mapping = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
    years = {int(item) for item in re.findall(r"(?:大|第)?([1-6])\s*年", value)}
    for chinese, number in mapping.items():
        if f"大{chinese}" in value or f"{chinese}年級" in value:
            years.add(number)
    if "新生" in value:
        years.add(1)
    return years


def _same_program(required: str, current: str) -> bool:
    if "進修" in required and "進修" in current:
        return True
    if "日間" in required and "日間" in current:
        return True
    if "在職" in required and "在職" in current:
        return True
    return required == current


def _department_matches(required: str, profile: StudentProfile) -> bool:
    terms = set(profile.research_keywords) | {
        profile.department,
        "電子",
        "電機",
        "電力",
        "能源",
        "資通訊",
        "資訊",
        "通訊",
        "工程",
        "理工",
        "電資",
    }
    return any(term and term in required for term in terms)


def _is_profile_special_status(value: str) -> bool:
    normalized = _normalize_status(value)
    return any(marker in normalized for marker in _PROFILE_SPECIAL_STATUS_MARKERS)


def _special_status_matches(required: str, owned: str) -> bool:
    normalized_required = _normalize_status(required)
    normalized_owned = _normalize_status(owned)
    return (
        normalized_required == normalized_owned
        or normalized_required in normalized_owned
        or normalized_owned in normalized_required
    )


def _normalize_status(value: str) -> str:
    return re.sub(r"[\s、，,；;／/或與及]+", "", value)


def _normalize_region(value: str) -> str:
    return value.replace("臺", "台").replace(" ", "")
