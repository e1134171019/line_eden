# -*- coding: utf-8 -*-

from collections import deque
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


# 完整稽核必須依頁面連結抓完所有偵測頁數。
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


# 龍華後續 DYNA 頁面產生的第 1 頁別名不得重新加入佇列。
def test_lhu_skips_dyna_first_page_alias() -> None:
    page_2 = "https://www.lhu.edu.tw/p/422-1000-4-2.php?Lang=zh-tw"
    page_3 = "https://www.lhu.edu.tw/p/422-1000-4-3.php?Lang=zh-tw"
    alias_page_1 = "https://www.lhu.edu.tw/p/422-1000-4-1.php?Lang=zh-tw"
    html = """
    <p>共3頁</p>
    <script>
    var option = {
      currentPage: 2,
      urlPrefix: 'https://www.lhu.edu.tw/p/422-1000-4-PAGE.php?Lang=zh-tw',
      totalPage: 3
    };
    </script>
    """
    collector = LhuCollector(BASE_URL, 10.0, "test", CollectionMode.FULL_AUDIT, 10)
    queue: deque[str] = deque()

    collector._enqueue_lhu_pages(queue, {BASE_URL, page_2}, html, page_2)

    assert alias_page_1 not in queue
    assert list(queue) == [page_3]


# 每日增量模式只讀最新入口頁，不回抓歷史頁。
def test_lhu_incremental_collects_first_page_only(monkeypatch: Any) -> None:
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
    assert calls == [BASE_URL]
    assert collector.lhu_diagnostic.completeness == "incremental"
    assert collector.lhu_diagnostic.pages_detected == 3
    assert collector.lhu_diagnostic.pages_succeeded == 1


# 建立含三頁導覽的最小 DYNA 列表 fixture。
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
