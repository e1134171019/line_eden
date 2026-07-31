# -*- coding: utf-8 -*-

from typing import cast

import httpx
from pytest import MonkeyPatch, raises

from src.catalogs.tun_2025_program_catalog import ScholarshipProgramWatch
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.http_client import DetailSafeHttpClient
from src.collectors.listing_paginator import ListingCrawlResult, ListingPage
from src.collectors.tun_program_watch_collector import (
    TunProgramWatchCollector,
    _ProgramPageFetcher,
    _build_diagnostic,
    _chunk_urls,
    _extract_program_notices,
    _fetch_text_with_retry,
    _group_programs_by_url,
)


def _program(
    program_id: str,
    title: str,
    url: str = "https://foundation.example/news",
) -> ScholarshipProgramWatch:
    return ScholarshipProgramWatch(
        program_id,
        title,
        "測試基金會",
        (title,),
        url,
        "verified",
    )


class _TimeoutThenSuccessClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_text(self, _: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise httpx.ReadTimeout("temporary timeout")
        return "<html>ok</html>"


class _FakeDetailClient:
    creations = 0

    def __init__(self, _: float, __: str) -> None:
        type(self).creations += 1
        self.fallback_hosts: set[str] = set()

    def __enter__(self) -> "_FakeDetailClient":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get_text(self, url: str) -> str:
        if url.endswith("/fail"):
            raise ValueError("invalid page")
        if url.endswith("/fallback"):
            self.fallback_hosts.add("foundation.example")
        return f"<html>{url}</html>"


# 同一主辦單位的方案必須合併為一次官方頁面請求。
def test_groups_programs_by_shared_official_url() -> None:
    programs = (
        _program("one", "第一獎學金"),
        _program("two", "第二獎學金"),
        _program("three", "第三獎學金", "https://other.example/news"),
    )

    grouped = _group_programs_by_url(programs)

    assert len(grouped) == 2
    assert [item.program_id for item in grouped["https://foundation.example/news"]] == [
        "one",
        "two",
    ]


# 暫時性 timeout 成功後不得繼續消耗剩餘重試次數。
def test_fetch_retries_one_transient_timeout(monkeypatch: MonkeyPatch) -> None:
    client = _TimeoutThenSuccessClient()
    monkeypatch.setattr(
        "src.collectors.tun_program_watch_collector.time.sleep",
        lambda _: None,
    )

    result = _fetch_text_with_retry(
        cast(DetailSafeHttpClient, client),
        "https://foundation.example/news",
    )

    assert result == "<html>ok</html>"
    assert client.calls == 2


# URL 以輪詢方式分成固定工作數，且不得漏失原始順序中的項目。
def test_chunk_urls_distributes_pages_across_workers() -> None:
    urls = tuple(f"page-{index}" for index in range(1, 8))

    chunks = _chunk_urls(urls, 3)

    assert chunks == (
        ("page-1", "page-4", "page-7"),
        ("page-2", "page-5"),
        ("page-3", "page-6"),
    )


# 批次分頁每個 chunk 只建立一個 client，並依輸入順序重組結果。
def test_parallel_page_fetcher_reuses_clients_and_records_errors(
    monkeypatch: MonkeyPatch,
) -> None:
    _FakeDetailClient.creations = 0
    monkeypatch.setattr(
        "src.collectors.tun_program_watch_collector.DetailSafeHttpClient",
        _FakeDetailClient,
    )
    fetcher = _ProgramPageFetcher(1.0, "test-agent", 2)
    urls = (
        "https://foundation.example/page/2",
        "https://foundation.example/fail",
        "https://foundation.example/fallback",
        "https://foundation.example/page/5",
    )

    pages, errors = fetcher.fetch_many(urls)

    assert list(pages) == [urls[0], urls[2], urls[3]]
    assert list(errors) == [urls[1]]
    assert "invalid page" in errors[urls[1]]
    assert fetcher.fallback_used is True
    assert _FakeDetailClient.creations == 2


# 非法工作數必須在啟動網路請求前失敗。
def test_program_watch_rejects_invalid_worker_count() -> None:
    with raises(ValueError, match="fetch_workers"):
        TunProgramWatchCollector(
            1.0,
            "test-agent",
            CollectionMode.FULL_AUDIT,
            20,
            0,
        )


# 群組診斷必須累計實際頁數、降級並列出實際失敗頁。
def test_watch_diagnostic_aggregates_complete_and_partial_crawls() -> None:
    page = ListingPage("https://one.example/news", "<html>one</html>")
    complete = ListingCrawlResult(
        (page,),
        1,
        1,
        1,
        "complete",
        "all_detected_pages_completed",
        tuple(),
    )
    partial = ListingCrawlResult(
        (page,),
        3,
        2,
        1,
        "partial",
        "parallel_fetch_errors",
        ("https://two.example/page/2（timeout）",),
    )

    diagnostic = _build_diagnostic(
        [("https://one.example/news", complete), ("https://two.example/news", partial)],
        parsed_rows=4,
        raw_rows=7,
        successful_programs=38,
        fallback_used=True,
    )

    assert diagnostic.completeness == "partial"
    assert diagnostic.pages_detected == 4
    assert diagnostic.pages_requested == 3
    assert diagnostic.pages_succeeded == 2
    assert diagnostic.rejected_rows == 3
    assert diagnostic.child_sources_succeeded == 38
    assert diagnostic.ssl_compatibility_fallback is True
    assert "parallel_fetch_errors" in diagnostic.error
    assert "page/2" in diagnostic.error
    assert "timeout" in diagnostic.error


# 官方公告列的西元日期應轉成 Scholarship 標準日期。
def test_extracts_gregorian_dated_program_notice() -> None:
    program = _program("energy", "能源工程獎學金")
    html = """
    <ul>
      <li><span>2026/09/15</span><a href="/news/88">能源工程獎學金開放申請</a></li>
    </ul>
    """

    records, matched = _extract_program_notices(
        html,
        "https://foundation.example/news",
        (program,),
    )

    assert matched >= 1
    assert len(records) == 1
    assert records[0].published_date == "2026-09-15"
    assert records[0].source_url == "https://foundation.example/news/88"


# 民國日期應轉成西元，確保後續期限推定具有正確年度。
def test_extracts_roc_dated_program_notice() -> None:
    program = _program("electronics", "電子人才獎學金")
    html = """
    <article>
      <h2><a href="notice-115">電子人才獎學金申請公告</a></h2>
      <time datetime="115年8月3日">115年8月3日</time>
    </article>
    """

    records, _ = _extract_program_notices(
        html,
        "https://foundation.example/news/",
        (program,),
    )

    assert len(records) == 1
    assert records[0].published_date == "2026-08-03"


# 靜態介紹頁即使出現方案名稱，沒有可靠日期也不得偽造當期公告。
def test_skips_static_program_page_without_date() -> None:
    program = _program("static", "長期助學金")
    html = "<main><h1>長期助學金</h1><p>本會長期推動學生扶助。</p></main>"

    records, matched = _extract_program_notices(
        html,
        "https://foundation.example/project",
        (program,),
    )

    assert matched == 1
    assert records == []
