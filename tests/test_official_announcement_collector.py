# -*- coding: utf-8 -*-

from src.collectors.official_announcement_collector import OfficialAnnouncementCollector


# 官方網站版型可不同，但只要公告區塊同時含日期、標題與連結即可解析。
def test_official_announcement_collector_parses_common_cards() -> None:
    html = """
    <main>
      <article class="news-card">
        <time>2026.06.01</time>
        <h3><a href="/scholarship/115-guide">115年甄選簡章及行政契約書</a></h3>
      </article>
      <li>
        <span>115年05月13日</span>
        <a href="/scholarship/result">115年錄取名單公告</a>
      </li>
      <a href="/about">關於本部</a>
    </main>
    """
    collector = OfficialAnnouncementCollector(
        source_code="moe-test",
        source_name="教育部測試獎學金",
        source_url="https://official.example.gov.tw/list",
        timeout_seconds=10.0,
        user_agent="ScholarshipAgentTest/1.0",
        link_keywords=("甄選", "錄取"),
    )

    records = collector._parse_html(html)

    assert len(records) == 2
    assert records[0].published_date == "2026-06-01"
    assert records[0].title == "教育部測試獎學金｜115年甄選簡章及行政契約書"
    assert records[0].source_url == "https://official.example.gov.tw/scholarship/115-guide"
    assert records[1].published_date == "2026-05-13"


# 民國年日期要轉成西元，錯誤日期不得產生公告。
def test_official_announcement_collector_normalizes_roc_date() -> None:
    html = """
    <div><span>115/09/03</span><a href="notice/1">獎助學金申請公告</a></div>
    <div><span>115/13/40</span><a href="notice/2">獎助學金錯誤日期</a></div>
    """
    collector = OfficialAnnouncementCollector(
        source_code="cip-test",
        source_name="原民會大專校院獎助學金",
        source_url="https://official.example.gov.tw/news/",
        timeout_seconds=10.0,
        user_agent="ScholarshipAgentTest/1.0",
        link_keywords=("獎助學金",),
    )

    records = collector._parse_html(html)

    assert len(records) == 1
    assert records[0].published_date == "2026-09-03"
