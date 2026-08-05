# -*- coding: utf-8 -*-

from src.ai.gemini_requirement_extractor import (
    GeminiRequirementExtraction,
    RequirementEvidence,
)
from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_RESOLVED
from src.evaluators.eligibility_evaluator import ELIGIBLE, REVIEW, EligibilityEvaluator
from src.evaluators.manual_check_extractor import extract_manual_checks
from src.evaluators.structured_eligibility_evaluator import StructuredEligibilityEvaluator
from src.models.evaluator_input import EvaluatorInput
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


def _profile(*, residence: str = "新北市新莊區") -> StudentProfile:
    return StudentProfile(
        school="龍華科技大學",
        degree_level="學士",
        program_type="進修部四技",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.6,
        conduct_grade=86,
        class_rank=1,
        class_size=17,
        residence=residence,
        special_statuses=tuple(),
        research_keywords=("電子", "資訊", "通訊", "AI", "工業應用"),
        nationality="中華民國",
        enrollment_status="在學",
        residence_years=5,
        academic_year_average=90.34,
        latest_semester_average=90.6,
        latest_conduct_grade=86,
        latest_class_rank=1,
        latest_class_size=17,
        has_failed_courses=False,
        has_major_discipline=False,
    )


def _extraction(
    *,
    other_required_conditions: list[str],
    residence_requirement: str | None = None,
) -> GeminiRequirementExtraction:
    return GeminiRequirementExtraction(
        document_type="scholarship_rules",
        criteria_complete=True,
        needs_more_pages=False,
        degree_levels=["大學生"],
        residence_requirement=residence_requirement,
        other_required_conditions=other_required_conditions,
        evidence=[RequirementEvidence(page=1, text="申請資格與應備資料")],
    )


# 自學計畫是申請後可準備的文件，不是申請人既有身分門檻。
def test_legacy_evaluator_keeps_wang_yun_wu_eligible_with_plan_required() -> None:
    scholarship = Scholarship.from_raw(
        "tun-program-wang-yun-wu-self-study",
        "王雲五先生自學獎學金",
        "2026-08-01",
        "https://yunwu.org.tw/y/news/category/6",
        program_id="wang-yun-wu-self-study",
    )
    detail = EvaluatorInput(
        body_text="申請對象為大學生。申請人須提出完整自學計畫書。",
        rules_status=RULES_STATUS_RESOLVED,
    )

    decision = EligibilityEvaluator().evaluate(scholarship, detail, _profile())

    assert decision.status == ELIGIBLE
    assert any("自學計畫" in item for item in decision.manual_checks)


# Structured 路徑也必須把提案列為準備事項，而不是 unknown／review。
def test_structured_evaluator_keeps_proposal_program_eligible() -> None:
    result = StructuredEligibilityEvaluator().evaluate(
        _extraction(other_required_conditions=["申請人須提交社會關懷提案書"]),
        _profile(),
    )

    assert result.decision.status == ELIGIBLE
    assert any("提案" in item for item in result.decision.manual_checks)


# 已存在的研究經驗是歷史資格，不得被錯降成可事後補做的申請文件。
def test_historical_research_experience_remains_review() -> None:
    result = StructuredEligibilityEvaluator().evaluate(
        _extraction(other_required_conditions=["申請人須具備曾執行研究計畫經驗"]),
        _profile(),
    )

    assert result.decision.status == REVIEW


# 新莊戶籍符合時維持 eligible；申請期間由 period 軸另行判定。
def test_xinzhuang_residence_is_hard_eligible() -> None:
    result = StructuredEligibilityEvaluator().evaluate(
        _extraction(
            other_required_conditions=[],
            residence_requirement="設籍新北市新莊區滿1年",
        ),
        _profile(),
    )

    assert result.decision.status == ELIGIBLE


# 文向限永靖鄉，使用者戶籍在新莊時應明確不符合。
def test_wenxiang_residence_is_ineligible() -> None:
    result = StructuredEligibilityEvaluator().evaluate(
        _extraction(
            other_required_conditions=[],
            residence_requirement="限設籍彰化縣永靖鄉",
        ),
        _profile(),
    )

    assert result.decision.status == "ineligible"


# 文字抽取器要同時涵蓋自學計畫、研究提案與面試等準備程序。
def test_preparation_extractor_returns_actionable_notes() -> None:
    checks = extract_manual_checks(
        "須提出自學計畫書；另須提交研究提案並參加面試。"
    )

    assert any("自學計畫" in item for item in checks)
    assert any("提案" in item for item in checks)
    assert any("面試" in item for item in checks)
