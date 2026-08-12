# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    ADDITIONAL_SCHOLARSHIP_SOURCES,
    AdditionalSourceAdapterId,
)


def test_npu_and_nchu_use_only_their_verified_adapters() -> None:
    sources = {item.source_id: item for item in ADDITIONAL_SCHOLARSHIP_SOURCES}

    assert {
        source_id
        for source_id, item in sources.items()
        if item.adapter_id is AdditionalSourceAdapterId.NPU_LATESTEVENT_LIST
    } == {"npu-scholarship-portal"}
    assert {
        source_id
        for source_id, item in sources.items()
        if item.adapter_id is AdditionalSourceAdapterId.TADNEWS_CATEGORY_LIST
    } == {"nchu-external-scholarships"}
