# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    ADDITIONAL_SCHOLARSHIP_SOURCES,
    AdditionalSourceAdapterId,
)


def test_nfu_source_uses_osa_canonical_scholarship_listing() -> None:
    source = next(
        item
        for item in ADDITIONAL_SCHOLARSHIP_SOURCES
        if item.source_id == "nfu-scholarships"
    )

    assert source.entry_url == "https://osa.nfu.edu.tw/zh_tw/4/sclink/scholarship"
    assert "osa.nfu.edu.tw" in source.allowed_hosts
    assert source.adapter_id is AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST
    assert source.max_pages == 10
