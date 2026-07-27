# -*- coding: utf-8 -*-

from src.models.scholarship import Scholarship


# 驗證標題可正確分類為 loan。
def test_scholarship_category_loan() -> None:
    item = Scholarship.from_raw(
        "lhu",
        "115學年度第1學期就學貸款申辦公告",
        "2026-07-22",
        "https://example.com/loan",
    )
    assert item.category == "loan"


# 驗證標題可正確分類為 subsidy。
def test_scholarship_category_subsidy() -> None:
    item = Scholarship.from_raw(
        "lhu",
        "失業勞工子女就學補助公告",
        "2026-07-22",
        "https://example.com/subsidy",
    )
    assert item.category == "subsidy"


# 驗證標題可正確分類為 scholarship。
def test_scholarship_category_scholarship() -> None:
    item = Scholarship.from_raw(
        "lhu",
        "優秀學生獎學金公告",
        "2026-07-22",
        "https://example.com/scholarship",
    )
    assert item.category == "scholarship"
