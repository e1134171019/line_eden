# -*- coding: utf-8 -*-

from src.evaluators.eligibility_evaluator import ELIGIBLE, REVIEW, EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile


# 建立匿名電子工程進修部學生背景。
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
        research_keywords=("逆變器", "電力電子", "能源"),
    )


# 建立測試公告。
def _item(title: str) -> Scholarship:
    return Scholarship.from_raw("lhu", title, "2026-07-27", "https://example.com/item")


# 驗證電子郵件不會被誤判成電子工程背景相符。
def test_email_text_does_not_match_electronics_field() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("就學貸款相關公告"),
        "聯絡方式為電子郵件 service@example.com，詳細內容請見網站。",
        _profile(),
    )

    assert decision.status == REVIEW
    assert "電子／電力" not in decision.reason_text()


# 驗證正文有科系申請語境時仍會匹配電子背景。
def test_department_context_matches_electronics_field() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("專業人才獎學金"),
        "申請資格限電子、電機及能源相關科系在校生。",
        _profile(),
    )

    assert decision.status == ELIGIBLE
    assert "電子／電力" in decision.reason_text()


# 驗證標題本身具電力能源領域時可視為強證據。
def test_field_keyword_in_title_is_strong_evidence() -> None:
    decision = EligibilityEvaluator().evaluate(
        _item("台灣電力與能源工程協會獎學金"),
        "大專院校在校生可申請。",
        _profile(),
    )

    assert decision.status == ELIGIBLE
    assert "電子／電力" in decision.reason_text()
