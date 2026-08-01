# -*- coding: utf-8 -*-

from pathlib import Path
from typing import Any

from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.http_client import SafeHttpClient
from src.collectors.lhu_collector import LhuCollector

BASE_URL = "https://www.lhu.edu.tw/p/422-1000-4.php?Lang=zh-tw"


# 讀取本機 fixture 並驗證龍華公告解析結果。
def test_lhu_collector_parse_fixture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "lhu_scholarships.html"
    html = fixture_path.read_text(encoding="utf-8")
    collector = LhuCollector(
        source_url=BASE_URL,
        timeout_seconds=10.0,
        user_agent="ScholarshipAgentTest/1.0",
    )

    records = collector._parse_html(html)

    assert len(records) == 2
    assert records[0].published_date == "2026-07-22"
    assert records[0].title == "115學年度第1學期日間部學生就學貸款申辦公告"
    assert records[0].source_url.startswith("https://www.lhu.edu.tw/")
    assert records[1].published_date == "2026-07-16"


# 完整稽核必須透過共用 paginator 抓完所有偵測頁數。
def test_lhu_full_audit_collects_all_detected_pages(monkeypatch: Any) -> None:
    page_2 = f"{BASE_URL}&page=2"
    page_3 = f"{BASE_URL}&page=3"
    pages = {
        BASE_URL: _page_html(1, "2026-07-30", page_2, page_3),
        page_2: _page_html(2, "2026-07-29", page_2, page_3),
        page_3: _page_html(3, "2026-07-28", page_2, page_3),
    }
    calls: list[str] = []

    def fake_get_text(_: SafeHttpClient, url: str) -> str:
        calls.append(url)
        return pages[url]

    monkeypatch.setattr(SafeHttpClient, "get_text", fake_get_text)
    collector = LhuCollector(
        BASE_URL,
        10.0,
        "test",
        CollectionMode.FULL_AUDIT,
        10,
    )

    records = collector._collect_lhu()

    assert [item.title for item in records] == ["第1頁獎學金", "第2頁獎學金", "第3頁獎學金"]
    assert calls == [BASE_URL, page_2, page_3]
    assert collector.lhu_diagnostic.completeness == "complete"
    assert collector.lhu_diagnostic.pages_detected == 3
    assert collector.lhu_diagnostic.pages_succeeded == 3


# LHU 使用 canonical 首頁時，共用 paginator 不得再抓 DYNA 第 1 頁別名。
def test_lhu_shared_paginator_skips_dyna_first_page_alias(monkeypatch: Any) -> None:
    page_2 = "https://www.lhu.edu.tw/p/422-1000-4-2.php?Lang=zh-tw"
    page_3 = "https://www.lhu.edu.tw/p/422-1000-4-3.php?Lang=zh-tw"
    alias_page_1 = "https://www.lhu.edu.tw/p/422-1000-4-1.php?Lang=zh-tw"
    pages = {
        BASE_URL: _dyna_page_html(1, "2026-07-30"),
        page_2: _dyna_page_html(2, "2026-07-29"),
        page_3: _dyna_page_html(3, "2026-07-28"),
    }
    calls: list[str] = []

    def fake_get_text(_: SafeHttpClient, url: str) -> str:
        calls.append(url)
        return pages[url]

    monkeypatch.setattr(SafeHttpClient, "get_text", fake_get_text)
    collector = LhuCollector(BASE_URL, 10.0, "test", CollectionMode.FULL_AUDIT, 10)

    records = collector._collect_lhu()

    assert len(records) == 3
    assert alias_page_1 not in calls
    assert calls == [BASE_URL, page_2, page_3]
    assert collector.lhu_diagnostic.completeness == "complete"


# 每日增量模式補抓第二頁，避免停跑一天後公告下沉而漏失。
def test_lhu_incremental_catches_up_second_page(monkeypatch: Any) -> None:
    page_2 = f"{BASE_URL}&page=2"
    page_3 = f"{BASE_URL}&page=3"
    calls: list[str] = []

    def fake_get_text(_: SafeHttpClient, url: str) -> str:
        calls.append(url)
        return _page_html(1, "2026-07-30", page_2, page_3)

    monkeypatch.setattr(SafeHttpClient, "get_text", fake_get_text)
    collector = LhuCollector(
        BASE_URL,
        10.0,
        "test",
        CollectionMode.INCREMENTAL,
        10,
    )

    records = collector._collect_lhu()

    assert len(records) == 1
    assert calls == [BASE_URL, page_2]
    assert collector.lhu_diagnostic.completeness == "incremental"
    assert collector.lhu_diagnostic.pages_detected == 3
    assert collector.lhu_diagnostic.pages_succeeded == 2


# 建立含三頁導覽的最小列表 fixture。
def _page_html(page: int, published_date: str, page_2: str, page_3: str) -> str:
    return f"""
    <table>
      <tr>
        <td>{published_date}</td>
        <td><a href="/notice/{page}">第{page}頁獎學金</a></td>
      </tr>
    </table>
    <nav class="pagination">
      <a href="{BASE_URL}">1</a>
      <a href="{page_2}">2</a>
      <a href="{page_3}">3</a>
      <a href="{page_2}">&gt;</a>
    </nav>
    <p>共3頁</p>
    """


# 建立會在後續頁產生第 1 頁別名的 DYNA fixture。
def _dyna_page_html(page: int, published_date: str) -> str:
    return f"""
    <table>
      <tr>
        <td>{published_date}</td>
        <td><a href="/notice/dyna-{page}">第{page}頁獎學金</a></td>
      </tr>
    </table>
    <p>共3頁</p>
    <script>
    var option = {{
      currentPage: {page},
      urlPrefix: 'https://www.lhu.edu.tw/p/422-1000-4-PAGE.php?Lang=zh-tw',
      totalPage: 3
    }};
    </script>
    """
