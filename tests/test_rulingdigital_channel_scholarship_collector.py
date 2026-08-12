# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    AdditionalScholarshipSource,
    AdditionalSourceAdapterId,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.rulingdigital_channel_scholarship_collector import (
    RulingDigitalChannelScholarshipCollector,
)


def _collector() -> RulingDigitalChannelScholarshipCollector:
    config = AdditionalScholarshipSource(
        source_id="rulingdigital-channel-test",
        display_name="RulingDigital channel 測試來源",
        entry_url="https://example.edu.tw/p/412-1000-63.php?Lang=zh-tw",
        allowed_hosts=("example.edu.tw",),
        review_reason="測試 RulingDigital /p/405 channel。",
        adapter_id=AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST,
        max_pages=5,
    )
    return RulingDigitalChannelScholarshipCollector(
        config,
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        5,
    )


def test_channel_keeps_only_same_host_p405_notice_links() -> None:
    collector = _collector()
    html = """
    <ul>
      <li>
        <span>2026-08-10</span>
        <a href="/p/405-1000-456%2Cc63.php?Lang=zh-tw">115年測試獎學金</a>
      </li>
      <li>
        <a href="/p/406-1000-457%2Cr63.php">115年另一筆獎學金</a>
      </li>
      <li>
        <a href="https://outside.example/p/405-1000-999%2Cc63.php">外站獎學金</a>
      </li>
    </ul>
    """

    records, raw_rows = collector._parse_html(html, collector.config.entry_url)

    assert raw_rows == 1
    assert [item.title for item in records] == ["115年測試獎學金"]
    assert records[0].published_date == "2026-08-10"
    assert records[0].detail_url == (
        "https://example.edu.tw/p/405-1000-456%2Cc63.php?Lang=zh-tw"
    )


def test_channel_does_not_treat_title_deadline_as_published_date() -> None:
    collector = _collector()

    records, raw_rows = collector._parse_html(
        """
        <div>
          <a href="/p/405-1000-456%2Cc63.php">
            台灣電力獎學金〖自行申請至115年8月15日止〗
          </a>
        </div>
        """,
        collector.config.entry_url,
    )

    assert raw_rows == 1
    assert len(records) == 1
    assert records[0].published_date == ""


def test_channel_accepts_notice_title_without_scholarship_marker() -> None:
    collector = _collector()

    records, raw_rows = collector._parse_html(
        '<a href="/p/405-1000-456%2Cc63.php">李長榮優秀學生獎</a>',
        collector.config.entry_url,
    )

    assert raw_rows == 1
    assert [item.title for item in records] == ["李長榮優秀學生獎"]
