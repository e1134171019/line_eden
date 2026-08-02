# -*- coding: utf-8 -*-

from src.evaluators.supplemental_profile_rules import (
    find_supplemental_exclusions,
    find_supplemental_matches,
    find_supplemental_unknowns,
)
from src.profiles.student_profile import StudentProfile


# 建立可依個別測試覆寫硬性背景欄位的學生資料。
def _profile(
    *,
    has_student_loan: bool | None = None,
    has_qualifying_volunteer_service: bool | None = None,
    birth_date: str = "",
) -> StudentProfile:
    return StudentProfile(
        school="龍華科技大學",
        degree_level="學士",
        program_type="進修部四技",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.6,
        conduct_grade=86.0,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電子", "電機"),
        has_student_loan=has_student_loan,
        has_qualifying_volunteer_service=has_qualifying_volunteer_service,
        birth_date=birth_date,
    )


WISDOMSHARE_RULE = (
    "申請資格以下三點皆需符合："
    "民國85年1月1日後出生之國內大專院校在校生。"
    "於114年第2學期含前任一學期曾申請就學貸款者。"
    "曾擔任本計畫合作社福單位之志工。"
)


# 必要背景未提供時必須維持 review 所需的 unknown，不得直接判符合。
def test_missing_student_loan_volunteer_and_birth_remain_unknown() -> None:
    unknowns = find_supplemental_unknowns(WISDOMSHARE_RULE, _profile())

    assert unknowns == [
        "公告要求曾申請就學貸款，但 profile.json 尚未確認。",
        "公告要求合作單位志工服務，但 profile.json 尚未確認。",
        "公告有出生日期限制，但 profile.json 未填有效 birth_date。",
    ]


# 已確認沒有就學貸款時，屬必要條件明確不符。
def test_confirmed_no_student_loan_is_hard_exclusion() -> None:
    exclusions = find_supplemental_exclusions(
        WISDOMSHARE_RULE,
        _profile(
            has_student_loan=False,
            has_qualifying_volunteer_service=True,
            birth_date="2000-01-02",
        ),
    )

    assert exclusions == ["公告要求曾申請就學貸款，但目前已確認不符合。"]


# 已確認沒有合作單位志工服務時，屬必要條件明確不符。
def test_confirmed_no_partner_volunteer_service_is_hard_exclusion() -> None:
    exclusions = find_supplemental_exclusions(
        WISDOMSHARE_RULE,
        _profile(
            has_student_loan=True,
            has_qualifying_volunteer_service=False,
            birth_date="2000-01-02",
        ),
    )

    assert exclusions == ["公告要求合作單位志工服務，但目前已確認不符合。"]


# 出生日期等於門檻不符合「後出生」，必須判硬性不符。
def test_birth_date_equal_to_threshold_is_hard_exclusion() -> None:
    exclusions = find_supplemental_exclusions(
        WISDOMSHARE_RULE,
        _profile(
            has_student_loan=True,
            has_qualifying_volunteer_service=True,
            birth_date="1996-01-01",
        ),
    )

    assert exclusions == ["公告限 1996-01-01 後出生，與目前生日不符。"]


# 三項必要條件都確認符合時，應產生三項正向證據且不留 unknown。
def test_confirmed_student_loan_volunteer_and_birth_match() -> None:
    profile = _profile(
        has_student_loan=True,
        has_qualifying_volunteer_service=True,
        birth_date="2000-01-02",
    )

    assert find_supplemental_exclusions(WISDOMSHARE_RULE, profile) == []
    assert find_supplemental_unknowns(WISDOMSHARE_RULE, profile) == []
    assert find_supplemental_matches(WISDOMSHARE_RULE, profile) == [
        "已確認曾申請就學貸款。",
        "已確認具合作單位志工服務。",
        "出生日期晚於 1996-01-01，符合公告限制。",
    ]