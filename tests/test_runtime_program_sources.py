# -*- coding: utf-8 -*-

from src.automation.source_health_artifact import SEVERE_PROGRAM_STATUSES
from src.catalogs.runtime_program_sources import runtime_resolved_programs
from src.matchers.program_name_matcher import match_programs
from src.models.source_quality import SourceUrlType


def _by_id(program_id: str):
    return next(
        item for item in runtime_resolved_programs() if item.program_id == program_id
    )


# Production 使用的 38 項來源不得遺漏或重複。
def test_runtime_source_contract_has_all_38_programs() -> None:
    programs = runtime_resolved_programs()

    assert len(programs) == 38
    assert len({item.program_id for item in programs}) == 38


# 已由 production 證明失效的入口必須改成可追蹤的正式來源。
def test_runtime_source_patches_use_verified_entry_types() -> None:
    assert _by_id("songliang-aid").official_url.endswith("/scholarship01")
    assert _by_id("buddha-charity-progress").source_url_type is SourceUrlType.RELAY_DETAIL
    assert _by_id("yonglin-hope").source_url_type is SourceUrlType.RELAY_DETAIL
    assert _by_id("sunshine-scholarship").official_url == "https://scls.sunshine.org.tw/"
    assert _by_id("dapeng-aid").source_url_type is SourceUrlType.RELAY_LIST
    assert _by_id("hndasset-wenxiang").source_url_type is SourceUrlType.RELAY_LIST


# 真實網站年度標題不得再落入 matcher_miss。
def test_live_titles_match_their_programs() -> None:
    cases = (
        (
            "tf4dr-aid",
            "本會114學年度第2學期『助學金』自115年2月10日起受理申請",
        ),
        (
            "hsinrong-emergency-aid",
            "財團法人福田文教基金會114年度欣榮圖書館急難學生助學金申請辦法",
        ),
        (
            "lovepeace-disadvantaged",
            "財團法人祥和文教基金會114年度優秀清寒獎學金獎助學金申請",
        ),
    )

    for program_id, title in cases:
        program = _by_id(program_id)
        result = match_programs(title, (program,))
        assert result.matched, (program_id, result)


# live contract 必須阻擋名稱漏抓與方案競爭模糊。
def test_matcher_failures_are_severe_source_statuses() -> None:
    assert "matcher_miss" in SEVERE_PROGRAM_STATUSES
    assert "match_ambiguous" in SEVERE_PROGRAM_STATUSES
