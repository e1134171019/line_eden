# -*- coding: utf-8 -*-

from pathlib import Path

from src.collectors.lhu_collector import LhuCollector


# 讀取本機 fixture 並驗證龍華公告解析結果。
def test_lhu_collector_parse_fixture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "lhu_scholarships.html"
    html = fixture_path.read_text(encoding="utf-8")
    collector = LhuCollector(
        source_url="https://www.lhu.edu.tw/p/422-1000-4.php?Lang=zh-tw",
        timeout_seconds=10.0,
        user_agent="ScholarshipAgentTest/1.0",
    )

    records = collector._parse_html(html)

    assert len(records) == 2
    assert records[0].published_date == "2026-07-22"
    assert records[0].title == "115學年度第1學期日間部學生就學貸款申辦公告"
    assert records[0].source_url.startswith("https://www.lhu.edu.tw/")
    assert records[1].published_date == "2026-07-16"
