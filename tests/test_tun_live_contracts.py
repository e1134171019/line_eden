# -*- coding: utf-8 -*-

from src.catalogs.tun_live_contracts import LIVE_PROGRAM_CONTRACTS, live_contract
from src.models.source_quality import SourceUrlType


def test_live_contracts_cover_reported_failures_and_songliang() -> None:
    expected = {
        "tf4dr-aid",
        "hsinrong-emergency-aid",
        "lovepeace-disadvantaged",
        "buddha-charity-progress",
        "yonglin-hope",
        "sunshine-scholarship",
        "sunshine-wanzu",
        "dapeng-aid",
        "hndasset-wenxiang",
        "harmony-stability",
        "songliang-aid",
    }

    assert expected <= set(LIVE_PROGRAM_CONTRACTS)


def test_songliang_contract_forces_rules_page() -> None:
    contract = live_contract("songliang-aid")

    assert contract.force_replace is True
    assert contract.preferred_sources[0].url.endswith("/scholarship/scholarship01")
    assert contract.preferred_sources[0].source_url_type is SourceUrlType.EVERGREEN
    assert "助學金實施辦法" in contract.aliases


def test_failed_sources_have_cross_host_fallbacks() -> None:
    for program_id in (
        "buddha-charity-progress",
        "yonglin-hope",
        "sunshine-scholarship",
        "sunshine-wanzu",
        "dapeng-aid",
        "hndasset-wenxiang",
        "harmony-stability",
    ):
        contract = live_contract(program_id)
        assert contract.force_replace is True
        assert contract.preferred_sources
        assert all(item.url.startswith("https://") for item in contract.preferred_sources)


def test_sunshine_contracts_prioritize_current_discovery_and_relay() -> None:
    for program_id in ("sunshine-scholarship", "sunshine-wanzu"):
        contract = live_contract(program_id)
        assert contract.preferred_sources[0].url == (
            "https://www.sunshine.org.tw/news/announce"
        )
        assert contract.preferred_sources[0].source_url_type is SourceUrlType.LIST
        assert contract.preferred_sources[1].url == (
            "https://announce.yzu.edu.tw/index.php/tw/st/"
            "st-lgs20250828-1100-01"
        )
        assert contract.preferred_sources[1].source_url_type is (
            SourceUrlType.RELAY_DETAIL
        )
        assert contract.preferred_sources[2].url == "https://scls.sunshine.org.tw/"


def test_dapeng_uses_verified_live_detail_first() -> None:
    contract = live_contract("dapeng-aid")

    assert contract.preferred_sources[0].url == (
        "https://www.ntin.edu.tw/news_detail.aspx?id=50777"
    )
    assert contract.preferred_sources[0].source_url_type is SourceUrlType.RELAY_DETAIL
    assert "大鵬獎助學金" in contract.aliases


def test_wenxiang_prefers_current_115_relay() -> None:
    contract = live_contract("hndasset-wenxiang")

    assert contract.preferred_sources[0].url == (
        "https://osa.ndhu.edu.tw/p/406-1005-260542%2Cr402.php?Lang=zh-tw"
    )
    assert contract.preferred_sources[0].source_url_type is SourceUrlType.RELAY_DETAIL
    assert "115年度文向獎學金" in contract.aliases


def test_harmony_uses_latest_verifiable_school_relay() -> None:
    contract = live_contract("harmony-stability")

    assert contract.preferred_sources[0].url == (
        "https://www.hk.edu.tw/remote/HKlf_1238963/"
    )
    assert contract.preferred_sources[0].source_url_type is SourceUrlType.RELAY_DETAIL
    assert "和諧安定獎學金" in contract.aliases


def test_matcher_miss_contracts_add_source_scoped_aliases() -> None:
    assert "第2學期助學金" in live_contract("tf4dr-aid").aliases
    assert "欣榮圖書館急難學生助學金" in live_contract(
        "hsinrong-emergency-aid"
    ).aliases
    assert "祥和文教基金會獎助學金" in live_contract(
        "lovepeace-disadvantaged"
    ).aliases
