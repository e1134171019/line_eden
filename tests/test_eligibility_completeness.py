# -*- coding: utf-8 -*-

from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    EligibilityEvaluator,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


# 建立匿名進修部電子工程二年級學生背景。
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
        research_keywords=("電子", "電力電子", "能源"),
    )


# 建立測試公告。
def _item(title: str) -> Scholarship:
    return Scholarship.from_raw("fixture", title, "2026-07-27", "https://example.com/item")


# 大眾傳播科系且排除進修與在職專班時，不得只因成績符合而 eligible。
def test_chen_bo_sheng_style_notice_is_ineligible() -> None:
    detail = (
        "申請資格：國內各大學院校大眾傳播相關系所，大學部二年級以上在學學生，"
        "不含進修推廣部學士班暨學分班及各種在職專班學生，"
        "學業及操行成績平均80分以上。"
    )

    decision = EligibilityEvaluator().evaluate(
        _item("陳博生先生新聞獎學金"),
        detail,
        _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "進修" in decision.reason_text() or "科系" in decision.reason_text()


# 標題明確限定博士生時，學士生直接排除。
def test_doctoral_title_is_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("人文社會科學博士生菁英獎學金"),
        "請依期限完成線上申請。",
        _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "研究所" in decision.reason_text() or "博士" in decision.reason_text()


# 同一公告含一般學生獎與博士生獎時，不得把整筆公告視為博士生專屬。
def test_mixed_general_and_doctoral_awards_stay_review() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("李長榮優秀學生獎、李長榮博士生匹配獎學金"),
        "相關資訊請自行下載。",
        _profile(),
    )

    assert decision.status == REVIEW
    assert "研究所" not in decision.reason_text()


# 低(中低)收入戶括號縮寫必須展開成必要特殊身分。
def test_parenthesized_low_income_status_is_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("低(中低)收入戶學生購置電腦補助"),
        "對象：低收入戶及中低收入戶高中職以上在學學生。",
        _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "低收入戶" in decision.reason_text()


# 只確認成績但申請對象僅寫「學生」時，不足以成為 eligible。
def test_score_only_without_applicant_scope_stays_review() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("一般學生獎學金"),
        "申請對象為學生，學業平均80分以上。",
        _profile(),
    )

    assert decision.status == REVIEW
    assert "適用對象" in decision.reason_text()


# 明確包含大學生且成績符合時，仍可通過完整性護欄。
def test_general_college_scope_and_score_can_be_eligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("優秀在校生獎學金"),
        "大學生及研究生均可申請，學業平均不得低於80分。",
        _profile(),
    )

    assert decision.status == ELIGIBLE
