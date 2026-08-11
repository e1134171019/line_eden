# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    AdditionalScholarshipSource,
    AdditionalSourceAdapterId,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.rulingdigital_list_scholarship_collector import (
    RulingDigitalListScholarshipCollector,
)


def _collector() -> RulingDigitalListScholarshipCollector:
    config = AdditionalScholarshipSource(
        source_id="rulingdigital-test",
        display_name="RulingDigital 測試來源",
        entry_url="https://example.edu.tw/p/403-1000-123-1.php?Lang=zh-tw",
        allowed_hosts=("example.edu.tw",),
        review_reason="測試 RulingDigital 列表。",
        adapter_id=AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST,
        max_pages=5,
    )
    return RulingDigitalListScholarshipCollector(
        config,
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        5,
    )


def test_rulingdigital_list_keeps_only_same_host_p406_detail_links() -> None:
    collector = _collector()
    html = """
    <nav>
      <a href="/p/403-1000-123-1.php?Lang=zh-tw">校外獎助學金</a>
      <a href="https://outside.example/p/406-1000-999,r123.php">外站公告</a>
    </nav>
    <ul>
      <li>
        <span>2026-08-01</span>
        <a href="/p/406-1000-456%2Cr123.php?Lang=zh-tw">115-1 測試獎助學金</a>
      </li>
      <li>
        <span>115/07/29</span>
        <a href="/p/406-1000-457%2Cr123.php?Lang=zh-tw">教育部學產基金急難慰問金</a>
      </li>
    </ul>
    """

    records, raw_rows = collector._parse_html(html, collector.config.entry_url)

    assert raw_rows == 2
    assert [item.title for item in records] == [
        "115-1 測試獎助學金",
        "教育部學產基金急難慰問金",
    ]
    assert [item.published_date for item in records] == ["2026-08-01", "2026-07-29"]
    assert records[0].detail_url == (
        "https://example.edu.tw/p/406-1000-456%2Cr123.php?Lang=zh-tw"
    )


def test_rulingdigital_list_rejects_non_p406_internal_links() -> None:
    collector = _collector()

    records, raw_rows = collector._parse_html(
        """
        <a href="/p/404-1000-123.php">一般頁面</a>
        <a href="/p/403-1000-123-2.php">下一頁</a>
        <a href="/index.php">首頁</a>
        """,
        collector.config.entry_url,
    )

    assert records == []
    assert raw_rows == 0
