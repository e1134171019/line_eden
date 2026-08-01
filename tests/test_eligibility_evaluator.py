# -*- coding: utf-8 -*-

from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    REVIEW_SOURCE_INCOMPLETE,
    EligibilityEvaluator,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


# 建立符合目前使用情境的匿名測試背景。
def _build_profile() -> StudentProfile:
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
        research_keywords=("逆變器", "電力電子", "能源"),
    )


# 建立測試公告。
def _build_item(title: str) -> Scholarship:
    return Scholarship.from_raw(
        "lhu",
        title,
        "2026-07-27",
        "https://example.com/item",
    )


# 驗證日間部明確限定公告會排除進修部學生。
def test_day_program_only_is_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("學生獎學金"),
        "申請對象限本校日間部學生。",
        _build_profile(),
    )

    assert decision.status == INELIGIBLE
    assert "日間部" in decision.reason_text()


# 驗證同時接受日間部與進修部時不會誤判排除。
def test_day_and_evening_program_are_not_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("全校學生獎學金"),
        "本校日間部及進修部在校生均可申請。",
        _build_profile(),
    )

    assert decision.status == ELIGIBLE


# 驗證大學生與研究生均可申請時不會排除學士生。
def test_undergraduate_and_graduate_are_not_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("大專學生獎學金"),
        "大學生及研究生均可申請，電子相關科系優先。",
        _build_profile(),
    )

    assert decision.status == ELIGIBLE


# 驗證研究所明確限定公告會排除學士生。
def test_graduate_only_is_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("研究獎學金"),
        "申請對象限碩士班及博士班學生。",
        _build_profile(),
    )

    assert decision.status == INELIGIBLE
    assert "研究所" in decision.reason_text()


# 驗證特定家庭身分公告會在背景不符時排除。
def test_special_status_mismatch_is_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("癌友家庭子女育秧獎學金"),
        "申請對象為癌友家庭子女。",
        _build_profile(),
    )

    assert decision.status == INELIGIBLE
    assert "癌友家庭子女" in decision.reason_text()


# 驗證清寒只是優先條件時不會排除一般學生。
def test_special_status_preference_is_not_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("優秀學生獎學金"),
        "大專院校在校生均可申請，清寒學生優先但不限清寒身分。",
        _build_profile(),
    )

    assert decision.status == ELIGIBLE


# 驗證電子電力領域符合時可判硬性條件符合，成績另列人工確認。
def test_matching_field_and_grade_is_eligible_with_manual_check() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("電力與能源工程優秀學生獎學金"),
        "大專院校在校生，學業平均 80 分以上，電子工程相關科系可申請。",
        _build_profile(),
    )

    assert decision.status == ELIGIBLE
    assert "電子" in decision.reason_text() or "電力" in decision.reason_text()
    assert any("80" in item for item in decision.manual_checks)


# 驗證成績低於公告門檻不再自動判定硬性不符。
def test_grade_below_threshold_is_manual_check() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("高成就獎學金"),
        "申請人學業平均成績 95 分以上。",
        _build_profile(),
    )

    assert decision.status == REVIEW
    assert decision.review_kind == REVIEW_SOURCE_INCOMPLETE
    assert any("95" in item for item in decision.manual_checks)
    assert "95" not in decision.reason_text()


# 驗證「不得低於」文字也只抽成自行確認門檻。
def test_grade_not_lower_than_threshold_is_manual_check() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("高成就獎學金"),
        "大專院校在校生，申請人平均成績不得低於 95 分。",
        _build_profile(),
    )

    assert decision.status == ELIGIBLE
    assert any("95" in item for item in decision.manual_checks)


# 驗證排名門檻不再依 profile 自動判定。
def test_rank_threshold_is_manual_check() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("大專學生排名獎學金"),
        "大專院校在校生，班級排名須為前 5%。",
        _build_profile(),
    )

    assert decision.status == ELIGIBLE
    assert any("前 5%" in item for item in decision.manual_checks)


# 驗證條件不足的公告採保守待確認且預設不推播。
def test_insufficient_information_requires_review() -> None:
    decision = EligibilityEvaluator().evaluate(
        _build_item("希望獎助學金"),
        "詳細資格請參閱附件。",
        _build_profile(),
    )

    assert decision.status == REVIEW
    assert decision.review_kind == REVIEW_SOURCE_INCOMPLETE
