# -*- coding: utf-8 -*-

import re

from src.ai.gemini_requirement_extractor import GeminiRequirementExtraction
from src.evaluators import structured_eligibility_evaluator as target
from src.profiles.student_profile import StudentProfile

_YEAR_TOKEN = r"([1-6一二三四五六])"
_YEAR_EXCLUSION_MARKERS = ("不含", "不包括", "排除", "不得為", "非")
_DUPLICATE_AWARD_MARKERS = ("不得重複", "已獲得其他單位獎學金", "重複申請")
_CHINESE_YEARS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}


def install_structured_requirement_scope_guard() -> None:
    """安裝具排除作用域的 structured evaluator 條件組裝器。"""

    setattr(target.StructuredEligibilityEvaluator, "_conditions", _conditions)


def _conditions(
    self: target.StructuredEligibilityEvaluator,
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[target.ConditionResult]:
    _ = self
    results: list[target.ConditionResult] = []
    results.extend(target._program_conditions(extraction, profile))
    results.extend(target._degree_conditions(extraction, profile))
    results.extend(target._department_conditions(extraction, profile))
    results.extend(target._special_status_conditions(extraction, profile))
    results.extend(target._score_conditions(extraction))
    results.extend(target._residence_conditions(extraction, profile))
    results.extend(_year_conditions(extraction, profile))
    results.extend(_free_text_conditions(extraction, profile))
    return results


def _year_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[target.ConditionResult]:
    return [
        _year_condition(requirement, profile.year)
        for requirement in extraction.year_requirements
        if requirement.strip()
    ]


def _year_condition(requirement: str, current_year: int) -> target.ConditionResult:
    minimum = _bounded_year(requirement, "以上")
    if minimum is not None:
        matched = current_year >= minimum
        return _year_result(requirement, matched)

    maximum = _bounded_year(requirement, "以下")
    if maximum is not None:
        matched = current_year <= maximum
        return _year_result(requirement, matched)

    years = _year_values(requirement)
    if not years:
        return target.ConditionResult(
            "year",
            requirement,
            target.UNKNOWN,
            f"年級條件語意仍需人工確認：{requirement}",
        )

    if any(marker in requirement for marker in _YEAR_EXCLUSION_MARKERS):
        matched = current_year not in years
        reason = (
            "目前年級未落入公告排除範圍。"
            if matched
            else "目前年級屬於公告明確排除範圍。"
        )
        return target.ConditionResult(
            "year_exclusion",
            requirement,
            target.PASS if matched else target.FAIL,
            reason,
        )

    return _year_result(requirement, current_year in years)


def _year_result(requirement: str, matched: bool) -> target.ConditionResult:
    return target.ConditionResult(
        "year",
        requirement,
        target.PASS if matched else target.FAIL,
        "年級條件符合公告。" if matched else "目前年級不在公告允許範圍。",
    )


def _bounded_year(value: str, suffix: str) -> int | None:
    pattern = rf"(?:大|第)?{_YEAR_TOKEN}\s*(?:年級|年)?\s*(?:含)?{suffix}"
    match = re.search(pattern, value)
    return _year_number(match.group(1)) if match else None


def _year_values(value: str) -> set[int]:
    years = set(target._extract_years(value))
    range_pattern = (
        rf"(?:大|第)?{_YEAR_TOKEN}\s*(?:年級|年)?\s*(?:至|到|－|-|~)\s*"
        rf"(?:大|第)?{_YEAR_TOKEN}\s*(?:年級|年)?"
    )
    for match in re.finditer(range_pattern, value):
        start = _year_number(match.group(1))
        end = _year_number(match.group(2))
        years.update(range(min(start, end), max(start, end) + 1))
    return years


def _year_number(value: str) -> int:
    return _CHINESE_YEARS.get(value, int(value) if value.isdigit() else 0)


def _free_text_conditions(
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
) -> list[target.ConditionResult]:
    results = [
        _explicit_exclusion_condition(value, profile)
        for value in extraction.explicit_exclusions
        if value.strip()
    ]
    for value in extraction.other_required_conditions:
        known = _known_required_condition(value, profile)
        if known is not None:
            results.append(known)
            continue
        manual_checks = target.extract_manual_checks(value)
        if manual_checks:
            results.extend(
                target.ConditionResult("other_manual", value, target.MANUAL, check)
                for check in manual_checks
            )
            continue
        results.append(
            target.ConditionResult(
                "other_required",
                value,
                target.UNKNOWN,
                f"其他必要條件仍需人工確認：{value}",
            )
        )
    return results


def _explicit_exclusion_condition(
    value: str,
    profile: StudentProfile,
) -> target.ConditionResult:
    if any(marker in value for marker in ("新生", "大一", "一年級")):
        excluded = profile.degree_level == "學士" and profile.year == 1
        return _known_exclusion(value, excluded, "目前年級")
    if "休學" in value:
        if not profile.enrollment_status:
            return _manual_exclusion(value, "目前是否為休學狀態")
        return _known_exclusion(value, "休學" in profile.enrollment_status, "目前學籍")
    if "延畢" in value:
        if not profile.enrollment_status:
            return _manual_exclusion(value, "目前是否為延畢狀態")
        return _known_exclusion(value, "延畢" in profile.enrollment_status, "目前學籍")
    if "學分班" in value:
        return _known_exclusion(value, "學分班" in profile.program_type, "目前學制")
    if "空中大學" in value:
        return _known_exclusion(value, "空中大學" in profile.school, "目前學校")
    if any(marker in value for marker in _DUPLICATE_AWARD_MARKERS):
        received = profile.has_received_similar_scholarship
        if received is None:
            return _manual_exclusion(value, "本學年是否已獲其他單位獎學金")
        return _known_exclusion(value, received, "重複領取條件")
    return target.ConditionResult(
        "explicit_exclusion",
        value,
        target.UNKNOWN,
        f"明確排除條件仍需人工確認：{value}",
    )


def _known_required_condition(
    value: str,
    profile: StudentProfile,
) -> target.ConditionResult | None:
    if "不及格科目" in value or "無不及格" in value:
        failed = profile.has_failed_courses
        if failed is None:
            return _manual_requirement(value, "是否有不及格科目")
        return target.ConditionResult(
            "failed_courses",
            value,
            target.FAIL if failed else target.PASS,
            "目前有不及格科目。" if failed else "無不及格科目條件符合。",
        )
    if "推薦" in value:
        available = profile.can_obtain_recommendation
        if available is None:
            return None
        return target.ConditionResult(
            "recommendation",
            value,
            target.PASS if available else target.FAIL,
            "可取得所需推薦。" if available else "無法取得公告要求的推薦。",
        )
    return None


def _known_exclusion(
    requirement: str,
    excluded: bool,
    label: str,
) -> target.ConditionResult:
    return target.ConditionResult(
        "explicit_exclusion",
        requirement,
        target.FAIL if excluded else target.PASS,
        f"{label}命中公告排除條件。" if excluded else f"{label}未命中公告排除條件。",
    )


def _manual_exclusion(requirement: str, question: str) -> target.ConditionResult:
    return target.ConditionResult(
        "explicit_exclusion",
        requirement,
        target.MANUAL,
        f"請自行確認：{question}。",
    )


def _manual_requirement(requirement: str, question: str) -> target.ConditionResult:
    return target.ConditionResult(
        "other_manual",
        requirement,
        target.MANUAL,
        f"請自行確認：{question}。",
    )
