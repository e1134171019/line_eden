# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    ADDITIONAL_SCHOLARSHIP_SOURCES,
    AdditionalSourceAdapterId,
)


def test_nfu_source_keeps_reachable_university_listing_after_osa_tls_failure() -> None:
    source = next(
        item
        for item in ADDITIONAL_SCHOLARSHIP_SOURCES
        if item.source_id == "nfu-scholarships"
    )

    assert source.entry_url == "https://www.nfu.edu.tw/zh_tw/ann/art"
    assert source.allowed_hosts == ("nfu.edu.tw", "www.nfu.edu.tw")
    assert source.adapter_id is AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST
    assert source.max_pages == 10
