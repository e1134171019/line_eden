# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    ADDITIONAL_SCHOLARSHIP_SOURCES,
    AdditionalSourceAdapterId,
)


def test_verified_rulingdigital_sources_use_exact_adapter_contracts() -> None:
    sources = {item.source_id: item for item in ADDITIONAL_SCHOLARSHIP_SOURCES}

    assert {
        source_id
        for source_id, item in sources.items()
        if item.adapter_id is AdditionalSourceAdapterId.RULINGDIGITAL_CHANNEL_LIST
    } == {
        "utaipei-external-scholarships",
        "knu-external-scholarships",
    }
    assert sources["niu-scholarships"].adapter_id is (
        AdditionalSourceAdapterId.RULINGDIGITAL_LIST
    )
    assert sources["niu-scholarships"].entry_url == (
        "https://niuosa.niu.edu.tw/p/403-1004-1440-1.php"
    )
    assert sources["ncue-external-scholarships"].adapter_id is (
        AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST
    )
