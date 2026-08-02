# -*- coding: utf-8 -*-

from src.ai.gemini_requirement_extractor import (
    GeminiRequirementExtraction,
    RequirementEvidence,
)
from src.evaluators.eligibility_evaluator import ELIGIBLE, INELIGIBLE
from src.evaluators.structured_eligibility_evaluator import (
    PASS,
    StructuredEligibilityEvaluator,
)
from src.profiles.student_profile import StudentProfile


def _profile(*, year: int = 2) -> StudentProfile:
    return StudentProfile(
        school="龍華科技大學",
        degree_level="學士",
        program_type="進修部四技",
        department="電子工程系",
        year=year,
        employed=True,
        average_grade=90.34,
        conduct_grade=86,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電子", "電機", "電力", "能源", "資通訊"),
        nationality="中華民國",
        enrollment_status="在學",
        academic_year_average=90.34,
        latest_semester_average=90.6,
        latest_conduct_grade=86,
        latest_class_rank=1,
        latest_class_size=17,
        has_failed_courses=False,
        has_received_similar_scholarship=False,
        special_statuses_confirmed=True,
    )


def _auden_extraction() -> GeminiRequirementExtraction:
    return GeminiRequirementExtraction(
        document_type="scholarship_rules",
        criteria_complete=True,
        needs_more_pages=False,
        degree_levels=["大學生", "研究生"],
        departments_included=["資(通)訊、生醫工程、環境永續相關系所"],
        year_requirements=[
            "不含學士班一年級新生、休學生、延畢生、學分班及空中大學學生"
        ],
        minimum_average_grade=85,
        minimum_conduct_grade=80,
        rank_requirement="學士班學期學科總平均85分以上且系所排名前10%",
        explicit_exclusions=[
            "學士班一年級新生",
            "休學生",
            "延畢生",
            "學分班",
            "空中大學學生",
            "該學年若已獲得其他單位獎學金者，不得重複申請本獎學金",
        ],
        other_required_conditions=["須無不及格科目"],
        evidence=[
            RequirementEvidence(
                page=1,
                text="不含學士班一年級新生；學士班平均85分以上且排名前10%",
            )
        ],
    )


def test_auden_freshman_exclusion_allows_second_year_student() -> None:
    result = StructuredEligibilityEvaluator().evaluate(_auden_extraction(), _profile())

    assert result.decision.status == ELIGIBLE
    assert not any("年級不在" in reason for reason in result.decision.reasons)
    year_conditions = [item for item in result.conditions if item.field.startswith("year")]
    assert year_conditions
    assert all(item.status == PASS for item in year_conditions)


def test_auden_freshman_exclusion_rejects_first_year_student() -> None:
    result = StructuredEligibilityEvaluator().evaluate(
        _auden_extraction(),
        _profile(year=1),
    )

    assert result.decision.status == INELIGIBLE
    assert "排除範圍" in result.decision.reason_text()


def test_minimum_year_requirement_accepts_higher_years() -> None:
    extraction = _auden_extraction().model_copy(
        update={
            "year_requirements": ["現讀大二含以上在學學生"],
            "explicit_exclusions": [],
        }
    )

    result = StructuredEligibilityEvaluator().evaluate(extraction, _profile(year=3))

    assert result.decision.status == ELIGIBLE
