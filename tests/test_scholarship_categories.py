# -*- coding: utf-8 -*-

from src.models.scholarship import Scholarship


# 建立指定標題的公告分類結果。
def _category(title: str) -> str:
    item = Scholarship.from_raw(
        "fixture",
        title,
        "2026-07-28",
        "https://example.test/notice",
    )
    return item.category


# 獎助學金複合名稱仍屬獎學金類。
def test_classifies_award_scholarship() -> None:
    assert _category("大專學生獎助學金") == "scholarship"


# 純助學金應與獎學金分開統計。
def test_classifies_student_aid() -> None:
    assert _category("弱勢學生助學金") == "student_aid"


# 就學貸款應獨立分類。
def test_classifies_student_loan() -> None:
    assert _category("學生就學貸款申辦公告") == "loan"


# 生活津貼或一般補助應列為補助類。
def test_classifies_subsidy() -> None:
    assert _category("學生生活津貼補助") == "subsidy"
