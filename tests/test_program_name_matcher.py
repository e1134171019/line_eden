# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import ScholarshipProgramWatch
from src.matchers.program_name_matcher import match_program


def _auden() -> ScholarshipProgramWatch:
    return ScholarshipProgramWatch(
        "auden-university-talent",
        "耀登炳南大專校院優秀人才獎學金",
        "耀登炳南教育基金會",
        ("耀登炳南大專校院優秀人才獎學金",),
        "https://www.auden.com.tw/news-4/",
        "verified",
    )


def test_equivalent_college_word_order_matches_auden() -> None:
    result = match_program(
        "【公告】2026耀登炳南大專院校優秀人才獎學金歡迎報名",
        _auden(),
    )

    assert result.matched is True
    assert result.method == "equivalent_alias"
    assert result.score == 95


def test_controlled_core_terms_match_abbreviated_title() -> None:
    result = match_program(
        "耀登炳南2026優秀人才大專獎學金",
        _auden(),
    )

    assert result.matched is True
    assert result.method == "core_terms"
    assert result.required_hits == ("耀登", "炳南")


def test_generic_scholarship_does_not_match_specific_program() -> None:
    result = match_program("2026大專院校優秀學生獎學金", _auden())

    assert result.matched is False
