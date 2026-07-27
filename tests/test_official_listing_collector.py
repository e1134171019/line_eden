# -*- coding: utf-8 -*-

from src.collectors.official_listing_collector import (
    OfficialListingCollector,
    OfficialSourceConfig,
)


def test_official_listing_parses_roc_date_and_filters_links() -> None:
    html = """
    <table>
      <tr><td><a href="/helpdreams/Grants_Content.aspx?id=1">115年度資訊獎學金</a></td><td>115-10-31</td></tr>
      <tr><td><a href="https://outside.example/item">外站獎學金</a></td><td>115-09-01</td></tr>
      <tr><td><a href="/about">一般消息</a></td><td>115-08-01</td></tr>
    </table>
    """
    collector = OfficialListingCollector(
        OfficialSourceConfig(
            "moe",
            "https://www.edu.tw/helpdreams/Grants.aspx",
            ("Grants_Content.aspx",),
        ),
        10.0,
        "test",
    )

    records = collector._parse_html(html)

    assert len(records) == 1
    assert records[0].published_date == "2026-10-31"
    assert records[0].title == "115年度資訊獎學金"
    assert records[0].source == "moe"
