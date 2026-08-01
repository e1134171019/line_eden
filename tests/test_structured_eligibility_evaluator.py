# -*- coding: utf-8 -*-

from src.ai.gemini_requirement_extractor import (
    GeminiRequirementExtraction,
    RequirementEvidence,
)
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    REVIEW,
    REVIEW_SOURCE_INCOMPLETE,
    EligibilityDecision,
)
from src.evaluators.structured_eligibility_evaluator import (
    INELIGIBLE,
    MANUAL,
    StructuredEligibilityEvaluator,
)
from src.profiles.student_profile import StudentProfile
from src.services.structured_shadow_comparison import compare_legacy_and_structured


def _profile(**updates: object) -> StudentProfile:
    values: dict[str, object] = {
        "school": "測試科技大學",
        "degree_level": "學士",
        "program_type": "進修部",
        "department": "電子工程系",
        "year": 2,
        "employed": True,
        "average_grade": 60.0,
        "conduct_grade": 60.0,
        "class_rank": 10,
        "class_size": 17,
        "residence": "新北市",
        "special_statuses": tuple(),
        "research_keywords": ("電力電子", "能源"),
    }
    values.update(updates)
    return StudentProfile(**values)  # type: ignore[arg-type]


def _extraction(**updates: object) -> GeminiRequirementExtraction:
    values: dict[str, object] = {
        "document_type": "scholarship_rules",
        "criteria_complete": True,
        "needs_more_pages": False,
        "departments_included": ["電子工程相關科系"],
        "minimum_average_grade": 80,
        "rank_requirement": "班級排名前10%",
        "evidence": [RequirementEvidence(page=1, text="電子工程相關科系，平均80分以上")],
    }
    values.update(updates)
    return GeminiRequirementExtraction(**values)


def test_complete_matching_extraction_is_eligible_with_manual_checks() -> None:
    result = StructuredEligibilityEvaluator().evaluate(_extraction(), _profile())

    assert result.decision.status == ELIGIBLE
    assert any("80" in item for item in result.decision.manual_checks)
    assert any("排名" in item for item in result.decision.manual_checks)
    assert any(item.status == MANUAL for item in result.conditions)


def test_excluded_evening_program_is_ineligible() -> None:
    extraction = _extraction(program_types_excluded=["進修部"])

    result = StructuredEligibilityEvaluator().evaluate(extraction, _profile())

    assert result.decision.status == INELIGIBLE
    assert "進修部" in result.decision.reason_text()


def test_incomplete_extraction_stays_review() -> None:
    extraction = _extraction(criteria_complete=False)

    result = StructuredEligibilityEvaluator().evaluate(extraction, _profile())

    assert result.decision.status == REVIEW
    assert result.decision.review_kind == REVIEW_SOURCE_INCOMPLETE
    assert "不完整" in result.decision.reason_text()


def test_unknown_other_required_condition_prevents_eligible() -> None:
    extraction = _extraction(other_required_conditions=["須由系主任推薦"])

    result = StructuredEligibilityEvaluator().evaluate(extraction, _profile())

    assert result.decision.status == REVIEW
    assert "系主任推薦" in result.decision.reason_text()


def test_special_status_list_is_any_of_not_all_of() -> None:
    extraction = _extraction(
        required_special_statuses=["低收入戶", "中低收入戶", "特殊境遇家庭"]
    )
    profile = _profile(special_statuses=("中低收入戶",))

    result = StructuredEligibilityEvaluator().evaluate(extraction, profile)

    assert result.decision.status == ELIGIBLE
    assert "中低收入戶" in result.decision.reason_text()


def test_missing_all_special_status_options_is_ineligible_once() -> None:
    extraction = _extraction(
        required_special_statuses=["低收入戶", "中低收入戶", "特殊境遇家庭"]
    )

    result = StructuredEligibilityEvaluator().evaluate(extraction, _profile())

    assert result.decision.status == INELIGIBLE
    assert result.decision.reason_text().count("任一身分") == 1


def test_shadow_comparison_never_changes_legacy_decision() -> None:
    legacy = EligibilityDecision(REVIEW, ("舊規則待確認。",))

    comparison = compare_legacy_and_structured(legacy, _extraction(), _profile())

    assert comparison.legacy_status == REVIEW
    assert comparison.structured_status == ELIGIBLE
    assert comparison.changed is True
