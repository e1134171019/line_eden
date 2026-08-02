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
from src.models.source_quality import SourceRisk, SourceUrlType


# 方案目錄必須完整保留文章列出的 38 項，且 program_id 不重複。
def test_tun_catalog_contains_exactly_38_unique_programs() -> None:
    assert len(TUN_2025_PROGRAMS) == 38
    assert len({item.program_id for item in TUN_2025_PROGRAMS}) == 38


# URL 品質模型必須完整覆蓋 38 項，不得留下隱含預設值。
def test_resolved_sources_cover_all_38_programs() -> None:
    programs = resolved_programs()

    assert len(programs) == 38
    assert len(monitorable_programs()) == 36
    assert len(core_covered_programs()) == 2
    assert unresolved_programs() == tuple()
    assert all(item.organizer_id for item in programs)
    assert all(item.expected_discovery for item in programs)
    assert all(item.last_verified_at == "2026-08-02" for item in programs)


# URL 健康與 URL 品質必須分離，38 項均有明確類型與風險。
def test_every_program_has_url_type_and_update_risk() -> None:
    programs = resolved_programs()

    assert all(isinstance(item.source_url_type, SourceUrlType) for item in programs)
    assert all(isinstance(item.update_risk, SourceRisk) for item in programs)
    assert all(item.source_url_type != SourceUrlType.PENDING for item in programs)
    assert all(item.source_url_type != SourceUrlType.WRONG for item in programs)


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
    assert by_id["tcb-foundation"].source_url_type == SourceUrlType.RELAY_LIST
    assert by_id["it-social-care"].official_status == SOURCE_RELAY
    assert by_id["it-social-care"].source_url_type == SourceUrlType.RELAY_DETAIL
    assert by_id["yonglin-hope"].official_status == SOURCE_CORE
    assert by_id["yonglin-hope"].source_url_type == SourceUrlType.CORE_COVERED
    assert by_id["yonglin-hope"].official_url == ""
    assert by_id["hndasset-wenxiang"].official_status == SOURCE_CORE
    assert by_id["hndasset-wenxiang"].official_url == ""


# 已核對的錯誤或低品質入口必須換成精準列表／常設頁。
def test_verified_entry_corrections_are_applied() -> None:
    by_id = {item.program_id: item for item in resolved_programs()}

    assert by_id["auden-university-talent"].official_url == (
        "https://www.auden.com.tw/news-4/"
    )
    assert by_id["lijin-taoyuan"].official_url == (
        "https://www.lijin.com.tw/Extend/Foundation/News"
    )
    assert by_id["wang-yun-wu-self-study"].official_url == (
        "https://yunwu.org.tw/y/news/category/6"
    )
    assert by_id["avc-talented-student"].official_url == (
        "https://www.avcgroup.org/Scholar"
    )
    assert by_id["cy-arch-aid"].official_url == (
        "https://www.cy-arch.com.tw/foundation/scholarship"
    )
    assert by_id["sunshine-scholarship"].official_url == (
        "https://scholarship.sunshine.org.tw/?cat=1"
    )
    assert by_id["heart-child"].official_url == (
        "https://www.ccft.org.tw/OnePage.aspx?tid=128"
    )


# 單篇年度轉載必須明確標記高風險，列表與常設頁可為低風險。
def test_url_quality_risk_matches_source_shape() -> None:
    by_id = {item.program_id: item for item in resolved_programs()}

    assert by_id["dapeng-aid"].source_url_type == SourceUrlType.RELAY_DETAIL
    assert by_id["dapeng-aid"].update_risk == SourceRisk.HIGH
    assert by_id["auden-university-talent"].source_url_type == SourceUrlType.LIST
    assert by_id["auden-university-talent"].update_risk == SourceRisk.LOW
    assert by_id["cy-arch-aid"].source_url_type == SourceUrlType.EVERGREEN
    assert by_id["cy-arch-aid"].update_risk == SourceRisk.LOW


# 每個可監測入口及其 fallback host 必須列入 allowed_hosts。
def test_allowed_hosts_cover_primary_and_fallback_urls() -> None:
    for item in monitorable_programs():
        assert item.allowed_hosts
        assert all(host for host in item.allowed_hosts)


# 同一主辦單位的多個方案應共用 organizer_id 與入口。
def test_shared_organizers_reuse_identity_and_entry() -> None:
    by_id = {item.program_id: item for item in resolved_programs()}

    assert by_id["ht-emergency"].organizer_id == by_id["ht-student-aid"].organizer_id
    assert by_id["cfh-graduate"].organizer_id == by_id["cfh-disabled-family"].organizer_id
    assert by_id["auden-innovation-research"].organizer_id == by_id[
        "auden-university-talent"
    ].organizer_id
    assert by_id["auden-innovation-research"].official_url == by_id[
        "auden-university-talent"
    ].official_url
