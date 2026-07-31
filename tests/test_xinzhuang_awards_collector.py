# -*- coding: utf-8 -*-

from typing import Any

from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.http_client import SafeHttpClient
from src.collectors.xinzhuang_awards_collector import XinzhuangAwardsCollector

BASE_URL = (
    "https://xinzhuangawards.ntpc.gov.tw/Schs/Frontend/RowView?"
    "alias=Cht_News&&id=MjE="
)


# 列表解析器應只保留 RowContent 公告並正規化西元與民國日期。
def test_xinzhuang_parser_extracts_official_notice_rows() -> None:
    html = """
    <table>
      <tbody>
        <tr>
          <td>2025年9月15日 <input type="checkbox"></td>
          <td>最新消息</td>
          <td>
            <a href="/Schs/Frontend/RowContent.aspx?alias=Cht_News&id=2061">
              新北市新莊區115年聯合優秀獎學金暨獎助學金實施計畫
            </a>
          </td>
        </tr>
        <tr>
          <td>114年09月19日</td>
          <td>最新消息</td>
          <td>
            <a href="/Schs/Frontend/RowContent?alias=Cht_News&id=2071">
              各高中、大學可提供之在學證明名單
            </a>
          </td>
        </tr>
      </tbody>
    </table>
    <a href="/Schs/Frontend/Login?alias=Cht_Login">登入</a>
    """
    collector = XinzhuangAwardsCollector(
        BASE_URL,
        10.0,
        "test",
        CollectionMode.FULL_AUDIT,
        10,
    )

    records, raw_rows = collector._parse_html_with_count(html)

    assert raw_rows == 2
    assert len(records) == 2
    assert records[0].source == "ntpc-xinzhuang-awards"
    assert records[0].published_date == "2025-09-15"
    assert records[0].source_url.endswith("RowContent.aspx?alias=Cht_News&id=2061")
    assert records[1].published_date == "2025-09-19"


# 完整稽核應跟隨同一列表的頁碼並完成所有偵測頁面。
def test_xinzhuang_full_audit_collects_all_pages(monkeypatch: Any) -> None:
    page_2 = f"{BASE_URL}&page=2"
    pages = {
        BASE_URL: _page_html(1, "2025年9月15日", page_2),
        page_2: _page_html(2, "2024年9月6日", page_2),
    }
    calls: list[str] = []

    def fake_get_text(_: SafeHttpClient, url: str) -> str:
        calls.append(url)
        return pages[url]

    monkeypatch.setattr(SafeHttpClient, "get_text", fake_get_text)
    collector = XinzhuangAwardsCollector(
        BASE_URL,
        10.0,
        "test",
        CollectionMode.FULL_AUDIT,
        10,
    )

    records = collector.collect()

    assert [item.title for item in records] == ["第1頁獎助學金", "第2頁獎助學金"]
    assert calls == [BASE_URL, page_2]
    assert collector.diagnostic.completeness == "complete"
    assert collector.diagnostic.pages_detected == 2
    assert collector.diagnostic.pages_succeeded == 2


# 每日增量模式只讀入口頁，不回抓歷史分頁。
def test_xinzhuang_incremental_reads_first_page_only(monkeypatch: Any) -> None:
    page_2 = f"{BASE_URL}&page=2"
    calls: list[str] = []

    def fake_get_text(_: SafeHttpClient, url: str) -> str:
        calls.append(url)
        return _page_html(1, "2025年9月15日", page_2)

    monkeypatch.setattr(SafeHttpClient, "get_text", fake_get_text)
    collector = XinzhuangAwardsCollector(
        BASE_URL,
        10.0,
        "test",
        CollectionMode.INCREMENTAL,
        10,
    )

    records = collector.collect()

    assert len(records) == 1
    assert calls == [BASE_URL]
    assert collector.diagnostic.completeness == "incremental"
    assert collector.diagnostic.pages_detected == 2
    assert collector.diagnostic.pages_succeeded == 1


# 建立含兩頁導覽的新莊訊息列表 fixture。
def _page_html(page: int, published_date: str, page_2: str) -> str:
    return f"""
    <table>
      <tbody>
        <tr>
          <td>{published_date}</td>
          <td>最新消息</td>
          <td>
            <a href="/Schs/Frontend/RowContent.aspx?alias=Cht_News&id={2000 + page}">
              第{page}頁獎助學金
            </a>
          </td>
        </tr>
      </tbody>
    </table>
    <nav class="pagination">
      <a href="{BASE_URL}">1</a>
      <a href="{page_2}">2</a>
      <a href="{page_2}" rel="next">下一頁</a>
    </nav>
    <p>共2頁</p>
    """
