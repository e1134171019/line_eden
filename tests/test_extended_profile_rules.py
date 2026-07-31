# -*- coding: utf-8 -*-

from src.evaluators.eligibility_evaluator import ELIGIBLE, INELIGIBLE, REVIEW
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


def _profile(**updates: object) -> StudentProfile:
    values: dict[str, object] = {
        "school": "龍華科技大學",
        "degree_level": "學士",
        "program_type": "進修部四技",
        "department": "電子工程系",
        "year": 2,
        "employed": True,
        "average_grade": 90.60,
        "conduct_grade": 86,
        "class_rank": 1,
        "class_size": 17,
        "residence": "新北市新莊區",
        "special_statuses": tuple(),
        "research_keywords": ("電力電子", "能源"),
        "nationality": "中華民國",
        "enrollment_status": "在學",
        "credits_earned": 67,
        "residence_years": 10.0,
        "cumulative_average": 88.03,
        "academic_year_average": 90.34,
        "latest_semester_average": 90.60,
        "latest_conduct_grade": 86,
        "latest_class_rank": 1,
        "latest_class_size": 17,
        "has_failed_courses": False,
        "has_major_discipline": False,
        "household_income": None,
        "household_size": 0,
        "has_received_similar_scholarship": None,
        "can_obtain_recommendation": None,
    }
    values.update(updates)
    return StudentProfile(**values)  # type: ignore[arg-type]


def _evaluate(detail: str, profile: StudentProfile | None = None) -> tuple[str, str]:
    item = Scholarship.from_raw(
        "fixture",
        "大專在校生獎學金申請公告",
        "2026-07-31",
        "https://example.test/scholarship",
    )
    decision = EligibilityEvaluator().evaluate(item, detail, profile or _profile())
    return decision.status, decision.reason_text()


def test_confirmed_profile_meets_full_basic_requirements() -> None:
    status, reason = _evaluate(
        "申請對象為大專在校生，須具中華民國國籍且未休學；"
        "累計修滿60學分以上；須設籍於新北市新莊區滿1年；"
        "各科均及格，且未受記過；請於2026/12/31前完成申請。"
    )

    assert status == ELIGIBLE, reason
    assert "中華民國國籍" in reason
    assert "60 學分" in reason
    assert "新莊區" in reason


def test_required_special_status_is_ineligible() -> None:
    status, reason = _evaluate(
        "申請對象限低收入戶大專在校生，請於2026/12/31前完成申請。"
    )

    assert status == INELIGIBLE
    assert "低收入戶" in reason


def test_special_status_preference_does_not_exclude() -> None:
    status, _ = _evaluate(
        "大專在校生均可申請，清寒學生優先；請於2026/12/31前完成申請。"
    )

    assert status == ELIGIBLE


def test_academic_year_threshold_uses_academic_year_average() -> None:
    status, reason = _evaluate(
        "申請對象為大專在校生，前一學年學業平均須達90.5分；"
        "請於2026/12/31前完成申請。"
    )

    assert status == INELIGIBLE
    assert "前一學年平均 90.34" in reason


def test_cumulative_threshold_uses_cumulative_average() -> None:
    status, reason = _evaluate(
        "申請對象為大專在校生，歷年平均成績須達89分；"
        "請於2026/12/31前完成申請。"
    )

    assert status == INELIGIBLE
    assert "累積平均 88.03" in reason


def test_credit_requirement_above_earned_credits_is_ineligible() -> None:
    status, reason = _evaluate(
        "申請對象為大專在校生，累計修滿68學分以上；"
        "請於2026/12/31前完成申請。"
    )

    assert status == INELIGIBLE
    assert "67" in reason
    assert "68" in reason


def test_missing_household_income_stays_review() -> None:
    status, reason = _evaluate(
        "申請對象為大專在校生，家庭年所得不得超過100萬元；"
        "請於2026/12/31前完成申請。"
    )

    assert status == REVIEW
    assert "家庭年所得" in reason


def test_unknown_recommendation_stays_review() -> None:
    status, reason = _evaluate(
        "申請對象為大專在校生，須由學校推薦；"
        "請於2026/12/31前完成申請。"
    )

    assert status == REVIEW
    assert "推薦" in reason
