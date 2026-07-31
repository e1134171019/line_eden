# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import (
    TUN_2025_PROGRAMS,
    TUN_DISCOVERY_URL,
)
from src.catalogs.tun_program_sources import (
    SOURCE_CORE,
    SOURCE_RELAY,
    core_covered_programs,
    monitorable_programs,
    resolved_programs,
    unresolved_programs,
)


# 方案目錄必須完整保留文章列出的 38 項，且 program_id 不重複。
def test_tun_catalog_contains_exactly_38_unique_programs() -> None:
    assert len(TUN_2025_PROGRAMS) == 38
    assert len({item.program_id for item in TUN_2025_PROGRAMS}) == 38


# 經官方頁替換與正式轉載補強後，38 項都必須有明確監測路徑。
def test_resolved_sources_cover_all_38_programs() -> None:
    programs = resolved_programs()

    assert len(programs) == 38
    assert len(monitorable_programs()) == 36
    assert len(core_covered_programs()) == 2
    assert unresolved_programs() == tuple()
    assert all(item.official_status != "pending" for item in programs)


# TUN 是發現線索，不得被當成正式資格或截止日來源。
def test_tun_page_is_discovery_reference_only() -> None:
    assert "university.1111.com.tw" in TUN_DISCOVERY_URL
    assert all(
        "university.1111.com.tw" not in item.official_url
        for item in resolved_programs()
    )


# 正式轉載與核心來源覆蓋必須明確標記，不能冒充主辦單位官網。
def test_source_kinds_are_explicit() -> None:
    by_id = {item.program_id: item for item in resolved_programs()}

    assert by_id["tcb-foundation"].official_status == SOURCE_RELAY
    assert "nutc.edu.tw" in by_id["tcb-foundation"].official_url
    assert by_id["it-social-care"].official_status == SOURCE_RELAY
    assert "yzu.edu.tw" in by_id["it-social-care"].official_url
    assert by_id["yonglin-hope"].official_status == SOURCE_CORE
    assert by_id["yonglin-hope"].official_url == ""
    assert by_id["hndasset-wenxiang"].official_status == SOURCE_CORE
    assert by_id["hndasset-wenxiang"].official_url == ""


# 真實 smoke 發現的逾時、憑證與 404 入口必須改用新頁面。
def test_failed_official_entries_are_replaced() -> None:
    by_id = {item.program_id: item for item in resolved_programs()}

    assert by_id["it-social-care"].official_url == (
        "https://announce.yzu.edu.tw/index.php/tw/st/st-lgs20260521-1630-01"
    )
    assert by_id["sunshine-scholarship"].official_url == (
        "https://scls.sunshine.org.tw/"
    )
    assert by_id["harmony-stability"].official_url == (
        "https://www.hk.edu.tw/remote/HKlf_1238963/"
    )
    assert by_id["auden-innovation-research"].official_url == (
        "https://www.auden.com.tw/news-4/"
    )


# 同一主辦單位的多個方案應共用一次官方網站請求。
def test_shared_organizers_reuse_official_entry() -> None:
    by_id = {item.program_id: item for item in resolved_programs()}

    assert by_id["ht-emergency"].official_url == by_id["ht-student-aid"].official_url
    assert by_id["cfh-graduate"].official_url == by_id["cfh-disabled-family"].official_url
    assert by_id["auden-innovation-research"].official_url == by_id[
        "auden-university-talent"
    ].official_url
