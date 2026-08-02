# -*- coding: utf-8 -*-

from src.evaluators.special_status_aliases import (
    find_alias_exclusions,
    find_alias_unknowns,
)
from src.profiles.student_profile import StudentProfile


# 建立符合目前學生背景的最小測試 profile。
def _profile(
    *,
    statuses: tuple[str, ...] = tuple(),
    confirmed: bool = True,
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
        special_statuses=statuses,
        research_keywords=("電子", "電力"),
        special_statuses_confirmed=confirmed,
    )


# 低收入戶只是優先排序時，一般學生仍保有申請資格。
def test_low_income_preference_does_not_exclude_general_student() -> None:
    text = "一般在校生均可申請，低收入戶及中低收入戶學生優先考量。"
    profile = _profile()

    assert find_alias_exclusions("一般學生獎學金", text, profile) == []
    assert find_alias_unknowns(text, profile) == []


# 明確要求至少一種弱勢身分時，已確認無身分者應判硬性不符。
def test_required_economic_status_excludes_confirmed_non_disadvantaged() -> None:
    text = "申請對象須具備低收入戶、中低收入戶或經濟弱勢任一身分。"
    profile = _profile()

    exclusions = find_alias_exclusions("助學金", text, profile)

    assert exclusions == ["須具備以下任一身分：低收入戶、中低收入戶、經濟弱勢。"]
    assert find_alias_unknowns(text, profile) == []


# 已具備其中一種必要身分時，不得因同句列出其他身分而排除。
def test_required_any_of_status_accepts_one_owned_status() -> None:
    text = "申請資格須具備低收入戶、中低收入戶或經濟弱勢任一身分。"
    profile = _profile(statuses=("低收入戶",))

    assert find_alias_exclusions("助學金", text, profile) == []
    assert find_alias_unknowns(text, profile) == []


# 身分欄位未提供時不得將空值解讀成確認沒有。
def test_missing_status_profile_remains_review() -> None:
    text = "申請對象須具備低收入戶或中低收入戶任一身分。"
    profile = _profile(confirmed=False)

    assert find_alias_exclusions("助學金", text, profile) == []
    assert find_alias_unknowns(text, profile) == [
        "公告要求經濟或特殊身分，但 profile.json 尚未確認相關身分。"
    ]


# 「以弱勢為原則」沒有說明一般生能否申請，應保留人工確認。
def test_ambiguous_disadvantaged_wording_remains_review() -> None:
    text = "本計畫以經濟弱勢為原則，詳細資格依審查結果辦理。"
    profile = _profile()

    assert find_alias_exclusions("助學金", text, profile) == []
    assert find_alias_unknowns(text, profile) == [
        "公告對經濟或特殊身分的要求語意不明，需人工確認。"
    ]


# 條件標題與身分分列多行時，仍須依「其中之一」解析為 any-of。
def test_cross_line_any_of_status_group() -> None:
    text = (
        "申請資格\n"
        "家庭經濟狀況符合下列條件其中之一：\n"
        "低收入戶或中低收入戶。\n"
        "家庭突遭變故。\n"
        "特殊境遇家庭。"
    )

    assert find_alias_exclusions("助學金", text, _profile()) == [
        "須具備以下任一身分：低收入戶、中低收入戶、遭逢變故、特殊境遇家庭。"
    ]
    assert find_alias_exclusions(
        "助學金",
        text,
        _profile(statuses=("特殊境遇家庭",)),
    ) == []


# 「共同申請條件」代表 all-of；具有其中一項不得掩蓋另一項缺失。
def test_cross_line_all_of_status_group() -> None:
    text = (
        "共同申請條件\n"
        "具中華民國國籍。\n"
        "家庭經濟弱勢，並經學校證明。\n"
        "須具原住民身分。"
    )

    assert find_alias_exclusions(
        "助學金",
        text,
        _profile(statuses=("經濟弱勢",)),
    ) == ["公告限定「原住民」身分。"]


# 頓號只是列舉符號，沒有任一、或、擇一等語意時不得自動視為 OR。
def test_enumeration_punctuation_alone_is_not_any_of() -> None:
    text = "申請資格須具備低收入戶、中低收入戶身分。"

    assert find_alias_exclusions("助學金", text, _profile(statuses=("低收入戶",))) == [
        "公告限定「中低收入戶」身分。"
    ]