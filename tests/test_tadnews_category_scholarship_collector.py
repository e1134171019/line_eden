# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    AdditionalScholarshipSource,
    AdditionalSourceAdapterId,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.tadnews_category_scholarship_collector import (
    TadnewsCategoryScholarshipCollector,
)


def _collector() -> TadnewsCategoryScholarshipCollector:
    config = AdditionalScholarshipSource(
        source_id="tadnews-test",
        display_name="Tadnews 測試來源",
        entry_url=(
            "https://example.edu.tw/osa/laa/sys/modules/tadnews/"
            "index.php?ncsn=4"
        ),
        allowed_hosts=("example.edu.tw",),
        review_reason="測試 Tadnews category contract。",
        adapter_id=AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST,
        max_pages=10,
    )
    return TadnewsCategoryScholarshipCollector(
        config,
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        10,
    )


def test_tadnews_keeps_numeric_nsn_in_same_category() -> None:
    collector = _collector()
    html = """
    <article>
      <span>2026-08-11</span>
      <a href="index.php?ncsn=4&nsn=123">企業優秀學生獎</a>
    </article>
    <a href="index.php?ncsn=4&g2p=2">2</a>
    <a href="index.php?ncsn=5&nsn=124">其他分類公告</a>
    <a href="index.php?ncsn=4&nsn=abc">非數字 nsn</a>
    """

    records, raw_rows = collector._parse_html(html, collector.config.entry_url)

    assert raw_rows == 1
    assert [item.title for item in records] == ["企業優秀學生獎"]
    assert records[0].published_date == "2026-08-11"


def test_tadnews_requires_configured_category_when_present() -> None:
    collector = _collector()
    records, raw_rows = collector._parse_html(
        '<a href="index.php?nsn=123">缺少 ncsn</a>',
        collector.config.entry_url,
    )

    assert raw_rows == 0
    assert records == []


def test_tadnews_does_not_use_deadline_in_title_as_publication_date() -> None:
    collector = _collector()
    records, raw_rows = collector._parse_html(
        '<a href="index.php?ncsn=4&nsn=123">某獎學金 115年10月1日截止</a>',
        collector.config.entry_url,
    )

    assert raw_rows == 1
    assert len(records) == 1
    assert records[0].published_date == ""
