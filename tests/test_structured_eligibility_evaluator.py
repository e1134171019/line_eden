# -*- coding: utf-8 -*-

from src.ai.gemini_requirement_extractor import (
    GeminiRequirementExtraction,
    RequirementEvidence,
)
from src.evaluators.eligibility_evaluator import ELIGIBLE, INELIGIBLE, REVIEW
from src.evaluators.structured_eligibility_evaluator import (
    FAIL,
    PASS,
    UNKNOWN,
    StructuredEligibilityEvaluator,
)
from src.profiles.student_profile import StudentProfile


def _profile() -> StudentProfile:
    return StudentProfile(
        school="測試科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.34,
        conduct_grade=85,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電力電子", "能源"),
    )


def _extraction(**overrides: object) -> GeminiRequirementExtraction:
    values: dict[str, object] = {
        "document_type": "scholarship_rules",
        "criteria_complete": True,
        "needs_more_pages": False,
        "applicant_groups": ["大專校院在校生"],
        "departments_included": ["電子工程相關科系"],
        "minimum_average_grade": 80,
        "evidence": [
            RequirementEvidence(
                source_kind="body",
                text="大專校院電子工程相關科系在校生，學業平均八十分以上。",
            )
        ],
    }
    values.update(overrides)
    return GeminiRequirementExtraction.model_validate(values)


def test_complete_structured_requirements_are_eligible() -> None:
    result = StructuredEligibilityEvaluator().evaluate(_extraction(), _profile())

    assert result.decision.status == ELIGIBLE
    assert any(item.status == PASS for item in result.checks)


def test_day_program_only_is_ineligible() -> None:
    extraction = _extraction(
        applicant_groups=[],
        departments_included=[],
        program_types_included=["日間部"],
    )

    result = StructuredEligibilityEvaluator().evaluate(extraction, _profile())

    assert result.decision.status == INELIGIBLE
    assert any(item.status == FAIL and item.field == "program_types_included" for item in result.checks)


def test_unstructured_other_condition_forces_review() -> None:
    extraction = _extraction(other_required_conditions=["須由系主任推薦"])

    result = StructuredEligibilityEvaluator().evaluate(extraction, _profile())

    assert result.decision.status == REVIEW
    assert any(item.status == UNKNOWN and item.field == "other_required_conditions" for item in result.checks)


def test_incomplete_extraction_forces_review() -> None:
    extraction = _extraction(criteria_complete=False)

    result = StructuredEligibilityEvaluator().evaluate(extraction, _profile())

    assert result.decision.status == REVIEW
    assert "不完整" in result.decision.reason_text()


def test_single_missing_special_status_is_ineligible() -> None:
    extraction = _extraction(required_special_statuses=["低收入戶"])

    result = StructuredEligibilityEvaluator().evaluate(extraction, _profile())

    assert result.decision.status == INELIGIBLE
    assert "低收入戶" in result.decision.reason_text()
