# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import ScholarshipProgramWatch
from src.catalogs.tun_program_sources import resolved_programs
from src.matchers.program_name_matcher import (
    AMBIGUOUS,
    MATCHED,
    NO_MATCH,
    match_program,
    match_programs,
)


def _auden() -> ScholarshipProgramWatch:
    return ScholarshipProgramWatch(
        "auden-university-talent",
        "耀登炳南大專校院優秀人才獎學金",
        "耀登炳南教育基金會",
        ("耀登炳南大專校院優秀人才獎學金",),
        "https://www.auden.com.tw/news-4/",
        "verified",
    )


# 取得同一 organizer_id 的實際來源契約方案。
def _organizer_programs(organizer_id: str) -> tuple[ScholarshipProgramWatch, ...]:
    return tuple(
        item for item in resolved_programs() if item.organizer_id == organizer_id
    )


def test_equivalent_college_word_order_matches_auden() -> None:
    result = match_program(
        "【公告】2026耀登炳南大專院校優秀人才獎學金歡迎報名",
        _auden(),
    )

    assert result.matched is True
    assert result.status == MATCHED
    assert result.method == "equivalent_alias"
    assert result.program_id == "auden-university-talent"


def test_controlled_core_terms_match_abbreviated_title() -> None:
    result = match_program(
        "耀登炳南2026優秀人才大專獎學金",
        _auden(),
    )

    assert result.matched is True
    assert result.method == "core_terms"
    assert result.required_hits == ("大專", "優秀人才")


def test_generic_scholarship_does_not_match_specific_program() -> None:
    result = match_program("2026大專院校優秀學生獎學金", _auden())

    assert result.matched is False
    assert result.status == NO_MATCH


def test_organizer_name_alone_does_not_select_auden_program() -> None:
    programs = _organizer_programs("auden-foundation")

    result = match_programs("耀登炳南教育基金會2026年度最新消息", programs)

    assert result.matched is False
    assert result.status == NO_MATCH
    assert result.score == 0


def test_auden_sibling_competition_selects_university_talent() -> None:
    programs = _organizer_programs("auden-foundation")

    result = match_programs(
        "2026耀登炳南大專院校優秀人才獎學金開放申請",
        programs,
    )

    assert result.status == MATCHED
    assert result.program_id == "auden-university-talent"
    assert result.score - result.second_best_score >= 15
    assert "創新研究" not in result.forbidden_hits


def test_auden_sibling_competition_selects_innovation_research() -> None:
    programs = _organizer_programs("auden-foundation")

    result = match_programs("第十二屆耀登炳南創新研究獎徵件公告", programs)

    assert result.status == MATCHED
    assert result.program_id == "auden-innovation-research"
    assert result.competing_program_id == "auden-university-talent"


def test_cfh_sibling_competition_distinguishes_three_programs() -> None:
    programs = _organizer_programs("cfh-foundation")

    graduate = match_programs("鄭豐喜研究所獎學金申請", programs)
    university = match_programs("鄭豐喜大學獎學金申請", programs)
    disabled = match_programs("鄭豐喜肢障者家庭子女獎學金", programs)

    assert graduate.program_id == "cfh-graduate"
    assert university.program_id == "cfh-university"
    assert disabled.program_id == "cfh-disabled-family"
    assert all(item.status == MATCHED for item in (graduate, university, disabled))


def test_ht_sibling_competition_does_not_confuse_student_aid() -> None:
    programs = _organizer_programs("ht-foundation")

    aid = match_programs("行天宮助學金申請辦法", programs)
    talented = match_programs("行天宮資優學生長期獎助學金", programs)
    emergency = match_programs("行天宮急難濟助申請", programs)

    assert aid.program_id == "ht-student-aid"
    assert talented.program_id == "ht-talented-long-term"
    assert emergency.program_id == "ht-emergency"


def test_sunshine_sibling_competition_uses_wanzu_term() -> None:
    programs = _organizer_programs("sunshine-foundation")

    general = match_programs("2026陽光獎學金申請公告", programs)
    wanzu = match_programs("萬足燒傷勞工子女大專生獎助學金", programs)

    assert general.program_id == "sunshine-scholarship"
    assert wanzu.program_id == "sunshine-wanzu"


def test_equal_sibling_alias_scores_return_ambiguous() -> None:
    programs = (
        ScholarshipProgramWatch(
            "same-one",
            "共同人才獎學金",
            "共同基金會",
            ("共同人才獎學金",),
            "https://example.test/news",
            "verified",
        ),
        ScholarshipProgramWatch(
            "same-two",
            "共同人才獎學金二",
            "共同基金會",
            ("共同人才獎學金",),
            "https://example.test/news",
            "verified",
        ),
    )

    result = match_programs("共同人才獎學金申請公告", programs)

    assert result.matched is False
    assert result.status == AMBIGUOUS
    assert result.score == result.second_best_score
