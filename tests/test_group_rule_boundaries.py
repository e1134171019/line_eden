# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_RESOLVED
from src.evaluators.eligibility_evaluator import ELIGIBLE, INELIGIBLE, EligibilityEvaluator
from src.models.scholarship import Scholarship
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


def _item() -> Scholarship:
    return Scholarship.from_raw(
        "lhu",
        "一般學生獎學金",
        "2026-07-27",
        "https://example.com/item",
    )


def _evaluate(detail: str):
    return EligibilityEvaluator().evaluate(
        _item(),
        detail,
        _profile(),
        rules_status=RULES_STATUS_RESOLVED,
    )


def test_long_day_program_clause_excludes_evening_student() -> None:
    detail = "申請對象限於本校各學院具有正式學籍且於申請期間持續在學之日間部學生。"

    decision = _evaluate(detail)

    assert decision.status == INELIGIBLE
    assert "日間部" in decision.reason_text()


def test_day_and_evening_groups_are_not_exclusive() -> None:
    detail = "本校日間部與進修部具有正式學籍之在校學生均可提出申請。"

    decision = _evaluate(detail)

    assert decision.status == ELIGIBLE


def test_preference_does_not_become_exclusive_requirement() -> None:
    detail = "本校學生均可申請，日間部學生於其他條件相同時優先考量。"

    decision = _evaluate(detail)

    assert decision.status == ELIGIBLE


def test_not_limited_to_day_program_is_not_exclusive() -> None:
    detail = "申請對象不限日間部，進修部學生亦可提出申請。"

    decision = _evaluate(detail)

    assert decision.status == ELIGIBLE
