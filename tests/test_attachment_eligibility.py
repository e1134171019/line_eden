# -*- coding: utf-8 -*-

from config import ATTACHMENT_TEXT_MARKER
from src.evaluators.eligibility_evaluator import ELIGIBLE, INELIGIBLE, EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


# 建立匿名進修部電子工程學生背景。
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


# 建立測試公告。
def _item(title: str) -> Scholarship:
    return Scholarship.from_raw("lhu", title, "2026-07-27", "https://example.com/item")


# 驗證附件已解析時不再因「請參閱附件」保留 review。
def test_resolved_attachment_can_make_notice_eligible() -> None:
    detail = (
        "申請資格請參閱附件。"
        f"{ATTACHMENT_TEXT_MARKER}"
        "申請資格限大專院校電子工程相關科系在校生，學業平均八十分以上。"
    )

    decision = EligibilityEvaluator().evaluate(_item("專業獎學金"), detail, _profile())

    assert decision.status == ELIGIBLE
    assert "參閱附件" not in decision.reason_text()


# 驗證「低收」同義詞會視為低收入戶必要身分。
def test_low_income_alias_is_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("低收及中低收入學生獎助學金"),
        "請符合資格者提出申請。",
        _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "低收入戶" in decision.reason_text()


# 驗證失業勞工子女限定公告不會停留在 review。
def test_unemployed_worker_children_is_ineligible() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("失業勞工子女助學補助"),
        "申請對象為失業勞工子女。",
        _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "失業勞工子女" in decision.reason_text()
