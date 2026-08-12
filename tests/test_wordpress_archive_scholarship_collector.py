# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    AdditionalScholarshipSource,
    AdditionalSourceAdapterId,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.wordpress_archive_scholarship_collector import (
    WordPressArchiveScholarshipCollector,
)


def _collector() -> WordPressArchiveScholarshipCollector:
    config = AdditionalScholarshipSource(
        source_id="wordpress-test",
        display_name="WordPress 測試來源",
        entry_url="https://example.com/category/scholarships/",
        allowed_hosts=("example.com",),
        review_reason="測試 WordPress archive。",
        adapter_id=AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST,
        max_pages=5,
    )
    return WordPressArchiveScholarshipCollector(
        config,
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        5,
    )


def test_wordpress_archive_parses_post_cards_and_ignores_sidebar_links() -> None:
    collector = _collector()
    html = """
    <main>
      <article class="post type-post">
        <time datetime="2026-06-29T09:00:00+08:00">2026 年 6 月 29 日</time>
        <h2 class="entry-title">
          <a href="/2026/06/29/power-scholarship/">115年台灣電力與能源工程協會獎學金</a>
        </h2>
      </article>
      <article class="post type-post">
        <time datetime="2026-06-18">2026 年 6 月 18 日</time>
        <h2 class="entry-title"><a href="/2026/06/18/activity/">一般活動公告</a></h2>
      </article>
    </main>
    <aside>
      <a href="/popular/scholarship/">熱門獎學金導覽</a>
    </aside>
    """

    records, raw_rows = collector._parse_html(html, collector.config.entry_url)

    assert raw_rows == 2
    assert len(records) == 1
    assert records[0].title == "115年台灣電力與能源工程協會獎學金"
    assert records[0].published_date == "2026-06-29"
    assert records[0].detail_url == "https://example.com/2026/06/29/power-scholarship/"


def test_wordpress_archive_rejects_page_without_post_structure() -> None:
    collector = _collector()

    records, raw_rows = collector._parse_html(
        '<nav><a href="/scholarship">獎學金</a></nav>',
        collector.config.entry_url,
    )

    assert records == []
    assert raw_rows == 0
