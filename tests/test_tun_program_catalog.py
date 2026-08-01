# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import (
    TUN_2025_PROGRAMS,
    TUN_DISCOVERY_URL,
    ProgramSourceType,
)
from src.catalogs.tun_program_sources import (
    SOURCE_CORE,
    core_covered_programs,
    monitorable_programs,
    resolved_programs,
    unresolved_programs,
)


# 方案目錄必須保留人工核對後的 30 項，且 program_id 不重複。
def test_tun_catalog_contains_exactly_30_unique_programs() -> None:
    assert len(TUN_2025_PROGRAMS) == 30
    assert len({item.program_id for item in TUN_2025_PROGRAMS}) == 30


# 經官方頁替換與正式轉載補強後，30 項都必須有明確監測路徑。
def test_resolved_sources_cover_all_30_programs() -> None:
    programs = resolved_programs()

    assert len(programs) == 30
    assert len(monitorable_programs()) == 25
    assert len(core_covered_programs()) == 5
    assert unresolved_programs() == tuple()
    assert all(item.official_status != "pending" for item in programs)


# TUN 是發現線索，不得被當成正式資格或截止日來源。
def test_tun_page_is_discovery_reference_only() -> None:
    assert "university.1111.com.tw" in TUN_DISCOVERY_URL
    assert all(
        "university.1111.com.tw" not in item.official_url
        for item in resolved_programs()
    )


# 官方入口與核心來源覆蓋必須明確標記，不能把舊年度轉載當成永久入口。
def test_source_kinds_are_explicit() -> None:
    by_id = {item.program_id: item for item in resolved_programs()}

    assert by_id["tcb-foundation"].source_type is ProgramSourceType.FIXED_PAGE
    assert "tcbbank.com.tw" in by_id["tcb-foundation"].official_url
    assert by_id["it-social-care"].source_type is ProgramSourceType.LISTING
    assert "csroc.org.tw" in by_id["it-social-care"].official_url
    assert by_id["yonglin-hope"].source_type is ProgramSourceType.DYNAMIC_PAGE
    assert "edu.yonglin.org.tw" in by_id["yonglin-hope"].official_url
    assert by_id["hndasset-wenxiang"].official_status == SOURCE_CORE
    assert by_id["hndasset-wenxiang"].official_url == ""
    assert by_id["hndasset-wenxiang"].source_type is ProgramSourceType.CORE_COVERED


# 人工核對的方案入口不得退回首頁、錯誤分類或單一舊年度轉載。
def test_verified_entries_use_precise_current_routes() -> None:
    by_id = {item.program_id: item for item in resolved_programs()}

    assert by_id["foxconn-scholarship-whale"].official_url == (
        "https://www.foxconnfoundation.org/plan/scholar/university"
    )
    assert by_id["wang-yun-wu-self-study"].official_url == (
        "https://yunwu.org.tw/y/news/category/6"
    )
    assert by_id["heart-child"].official_url == (
        "https://www.ccft.org.tw/List.aspx?tid=128"
    )
    assert by_id["auden-innovation-research"].official_url == (
        "https://www.auden.com.tw/news-4/"
    )


# 同一入口的多個方案應共用請求；不同辦法頁則必須保持分離。
def test_shared_organizers_reuse_official_entry() -> None:
    by_id = {item.program_id: item for item in resolved_programs()}

    assert by_id["ht-talented-long-term"].official_url != by_id["ht-student-aid"].official_url
    assert by_id["cfh-graduate"].official_url == by_id["cfh-disabled-family"].official_url
    assert by_id["auden-innovation-research"].official_url == by_id[
        "auden-university-talent"
    ].official_url


# 人工確認不採用的方案不得重新進入監測目錄。
def test_removed_programs_are_not_monitored() -> None:
    program_ids = {item.program_id for item in resolved_programs()}
    removed_program_ids = {
        "tf4dr-aid",
        "kumota-flying",
        "lijin-taoyuan",
        "hsinrong-emergency-aid",
        "cdf-vocational",
        "ht-emergency",
        "lovepeace-disadvantaged",
        "taishin-youth-volunteer",
    }

    assert program_ids.isdisjoint(removed_program_ids)
