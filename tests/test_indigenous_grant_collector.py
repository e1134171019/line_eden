# -*- coding: utf-8 -*-

from src.collectors.indigenous_grant_collector import IndigenousGrantCollector


# 專用 parser 應保留所有 /news/view/ 公告，後續再分類申請或資訊公告。
def test_indigenous_parser_keeps_all_news_links() -> None:
    html = """
    <table>
      <tr>
        <td>2026.07.06</td><td>獎學金公告</td>
        <td><a href="/news/view/101">115學年度第1學期申請期程公告</a></td>
      </tr>
      <tr>
        <td>2026.06.25</td><td>獎學金公告</td>
        <td><a href="/news/view/100">暑假作息公告</a></td>
      </tr>
    </table>
    """
    collector = IndigenousGrantCollector(
        "https://cipgrant.fju.edu.tw/news",
        10.0,
        "test",
    )

    records = collector._parse_html(html)

    assert len(records) == 2
    assert records[0].published_date == "2026-07-06"
    assert records[1].title == "暑假作息公告"
    assert records[1].published_date == "2026-06-25"
