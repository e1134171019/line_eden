# -*- coding: utf-8 -*-

from src.evaluators.notice_classifier import APPLICATION, RESULT, classify_notice
from src.evaluators.special_status_aliases import find_alias_exclusions
from src.profiles.student_profile import StudentProfile


def _profile(*statuses: str) -> StudentProfile:
    return StudentProfile(
        school="測試科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=None,
        conduct_grade=None,
        class_rank=None,
        class_size=None,
        residence="新北市",
        special_statuses=statuses,
        research_keywords=("電力電子",),
    )


def test_auden_application_title_wins_over_historical_result_links() -> None:
    kind = classify_notice(
        "耀登炳南大專院校優秀人才獎學金，歡迎推薦報名",
        (
            "申請資格：大專校院大學生。申請方式：線上報名。"
            "相關文章：2025年得獎名單、2024年獲獎名單。"
        ),
    )

    assert kind == APPLICATION


def test_result_title_still_has_priority_over_application_body() -> None:
    kind = classify_notice(
        "耀登炳南大專院校優秀人才獎學金得獎名單",
        "申請資格、申請方式與歷年辦法如下。",
    )

    assert kind == RESULT


def test_songliang_any_of_hard_status_is_required() -> None:
    reasons = find_alias_exclusions(
        "台灣松樑教育公益促進協會助學金",
        "救助對象：家庭清寒、經濟弱勢或遭逢變故之在學學生。",
        _profile(),
    )

    assert reasons == ["須具備以下任一身分：清寒、經濟弱勢、遭逢變故。"]


def test_songliang_any_of_accepts_one_owned_status() -> None:
    reasons = find_alias_exclusions(
        "台灣松樑教育公益促進協會助學金",
        "救助對象：家庭清寒、經濟弱勢或遭逢變故之在學學生。",
        _profile("家庭清寒"),
    )

    assert reasons == []
