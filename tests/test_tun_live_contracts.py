# -*- coding: utf-8 -*-

from src.catalogs.tun_live_contracts import LIVE_PROGRAM_CONTRACTS, live_contract
from src.models.source_quality import SourceUrlType


# Production 報告已證實的來源必須具備明確 live 契約。
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
        "songliang-aid",
    }

    assert expected <= set(LIVE_PROGRAM_CONTRACTS)


# 松樑必須直接抓實施辦法，不能再以入口頁領域文字判符合。
def test_songliang_contract_forces_rules_page() -> None:
    contract = live_contract("songliang-aid")

    assert contract.force_replace is True
    assert contract.preferred_sources[0].url.endswith("/scholarship/scholarship01")
    assert contract.preferred_sources[0].source_url_type is SourceUrlType.EVERGREEN
    assert "助學金實施辦法" in contract.aliases


# SSL 或 404 來源必須有不同 host 的正式備援。
def test_failed_sources_have_cross_host_fallbacks() -> None:
    for program_id in (
        "buddha-charity-progress",
        "yonglin-hope",
        "sunshine-scholarship",
        "sunshine-wanzu",
        "dapeng-aid",
    ):
        contract = live_contract(program_id)
        assert contract.force_replace is True
        assert contract.preferred_sources
        assert all(item.url.startswith("https://") for item in contract.preferred_sources)


# 陽光兩方案應優先檢查官方公告列表，再退回可連線申請入口。
def test_sunshine_contracts_prioritize_current_discovery() -> None:
    for program_id in ("sunshine-scholarship", "sunshine-wanzu"):
        contract = live_contract(program_id)
        assert contract.preferred_sources[0].url == (
            "https://www.sunshine.org.tw/news/announce"
        )
        assert contract.preferred_sources[0].source_url_type is SourceUrlType.LIST
        assert contract.preferred_sources[1].url == "https://scls.sunshine.org.tw/"


# 大鵬不得再先打已由 live runner 證明404的東華入口。
def test_dapeng_uses_verified_live_detail_first() -> None:
    contract = live_contract("dapeng-aid")

    assert contract.preferred_sources[0].url == (
        "https://www.ntin.edu.tw/news_detail.aspx?id=50777"
    )
    assert contract.preferred_sources[0].source_url_type is SourceUrlType.RELAY_DETAIL
    assert "大鵬獎助學金" in contract.aliases


# 三個 matcher miss 使用網站實際標題，不降低全域門檻。
def test_matcher_miss_contracts_add_source_scoped_aliases() -> None:
    assert "第2學期助學金" in live_contract("tf4dr-aid").aliases
    assert "欣榮圖書館急難學生助學金" in live_contract(
        "hsinrong-emergency-aid"
    ).aliases
    assert "祥和文教基金會獎助學金" in live_contract(
        "lovepeace-disadvantaged"
    ).aliases
