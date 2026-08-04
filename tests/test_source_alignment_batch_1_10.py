# -*- coding: utf-8 -*-

from dataclasses import replace

from src.catalogs.tun_live_contracts import live_contract
from src.catalogs.tun_program_sources import ResolvedProgramSource, resolved_programs
from src.matchers.program_name_matcher import match_program
from src.models.source_quality import SourceUrlType


def _source(program_id: str) -> ResolvedProgramSource:
    return next(item for item in resolved_programs() if item.program_id == program_id)


def _source_with_live_aliases(program_id: str) -> ResolvedProgramSource:
    source = _source(program_id)
    contract = live_contract(program_id)
    aliases = tuple(dict.fromkeys((*source.aliases, *contract.aliases)))
    return replace(source, aliases=aliases)


def test_cfh_combined_announcement_matches_both_program_contracts() -> None:
    title = "114年度「鄭豐喜〈研究所／大學〉獎學金」申請公告"

    for program_id in ("cfh-graduate", "cfh-university"):
        result = match_program(title, _source_with_live_aliases(program_id))

        assert result.matched is True
        assert result.program_id == program_id
        assert result.score >= 100


def test_lijin_actual_annual_title_matches_without_organizer_name() -> None:
    title = "114年度清寒獎助學金開放申請囉~~"

    result = match_program(title, _source_with_live_aliases("lijin-taoyuan"))

    assert result.matched is True
    assert result.program_id == "lijin-taoyuan"


def test_tainan_kaiji_uses_cross_year_relay_list() -> None:
    contract = live_contract("tainan-kaiji")

    assert contract.force_replace is True
    assert contract.preferred_sources[0].url == (
        "https://service.utaipei.edu.tw/p/412-1034-63.php?Lang=zh-tw"
    )
    assert contract.preferred_sources[0].source_url_type is SourceUrlType.RELAY_LIST


def test_kumota_card_title_locks_to_target_program() -> None:
    title = "114年度｜雲田乘風飛揚獎助學金計畫"

    result = match_program(title, _source("kumota-flying"))

    assert result.matched is True
    assert result.program_id == "kumota-flying"


def test_tcb_full_name_matches_but_alumni_foundation_does_not() -> None:
    source = _source("tcb-foundation")

    positive = match_program(
        "台中商業銀行文教基金會大專院校獎助學金",
        source,
    )
    negative = match_program(
        "中商校友文教基金會獎學金",
        source,
    )

    assert positive.matched is True
    assert negative.matched is False
