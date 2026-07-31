# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import (
    OFFICIAL_PENDING,
    OFFICIAL_VERIFIED,
    TUN_2025_PROGRAMS,
    TUN_DISCOVERY_URL,
    pending_programs,
    verified_programs,
)


# 方案目錄必須完整保留文章列出的 38 項，且 program_id 不重複。
def test_tun_catalog_contains_exactly_38_unique_programs() -> None:
    assert len(TUN_2025_PROGRAMS) == 38
    assert len({item.program_id for item in TUN_2025_PROGRAMS}) == 38
    assert len(verified_programs()) == 31
    assert len(pending_programs()) == 7


# TUN 是發現線索，不得被當成正式資格或截止日來源。
def test_tun_page_is_discovery_reference_only() -> None:
    assert "university.1111.com.tw" in TUN_DISCOVERY_URL
    assert all(
        "university.1111.com.tw" not in item.official_url
        for item in TUN_2025_PROGRAMS
    )


# 已驗證與待確認狀態必須和官方網址欄位一致。
def test_official_status_matches_official_url() -> None:
    for item in TUN_2025_PROGRAMS:
        if item.official_status == OFFICIAL_VERIFIED:
            assert item.official_url.startswith(("https://", "http://"))
        else:
            assert item.official_status == OFFICIAL_PENDING
            assert item.official_url == ""


# 同一主辦單位的多個方案應共用一次官方網站請求。
def test_shared_organizers_reuse_official_entry() -> None:
    by_id = {item.program_id: item for item in TUN_2025_PROGRAMS}

    assert by_id["ht-emergency"].official_url == by_id["ht-student-aid"].official_url
    assert by_id["cfh-graduate"].official_url == by_id["cfh-disabled-family"].official_url
    assert by_id["auden-innovation-research"].official_url == by_id[
        "auden-university-talent"
    ].official_url
