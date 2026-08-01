# -*- coding: utf-8 -*-

from typing import cast

import httpx
from pytest import MonkeyPatch, raises

from src.catalogs.tun_2025_program_catalog import (
    ProgramSourceType,
    ScholarshipProgramWatch,
)
from src.collectors.collection_diagnostics import CollectionMode, SourceAccessMode
from src.collectors.http_client import DetailSafeHttpClient
from src.collectors.listing_paginator import ListingCrawlResult, ListingPage
from src.collectors.tun_program_watch_collector import (
    TunProgramWatchCollector,
    _ProgramPageFetcher,
    _append_unique,
    _build_diagnostic,
    _build_target_diagnostics,
    _chunk_urls,
    _extract_program_notices,
    _extract_program_source_diagnostics,
    _fetch_text_with_retry,
    _group_programs_by_url,
    _semantic_target_status,
)
from src.models.scholarship import Scholarship


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


# 30 個邏輯方案必須與直接入口、核心涵蓋及唯一網站分開統計。
def test_program_watch_reports_real_monitoring_scope() -> None:
    targets = _build_target_diagnostics([], {}, [])

    assert len(targets) == 30
    assert sum(
        target.access_mode is SourceAccessMode.DIRECT for target in targets
    ) == 25
    assert sum(
        target.access_mode is SourceAccessMode.CORE_COVERED for target in targets
    ) == 5
    assert len({target.entry_url for target in targets if target.entry_url}) == 21
    assert len({target.domain for target in targets if target.domain}) == 20


# 核心來源涵蓋方案必須真的命中名稱，不能因設定為 covered 就自動成功。
def test_core_covered_program_requires_matching_evidence() -> None:
    evidence = Scholarship.from_raw(
        "moe-helpdreams-private",
        "115年度臺疆祖廟清寒優秀獎學金",
        "",
        "https://www.edu.tw/helpdreams/notice/1",
    )

    without_evidence = _build_target_diagnostics([], {}, [])
    with_evidence = _build_target_diagnostics([], {}, [], (evidence,))
    missing = next(target for target in without_evidence if target.target_id == "tainan-kaiji")
    matched = next(target for target in with_evidence if target.target_id == "tainan-kaiji")

    assert missing.is_succeeded is False
    assert "未命中" in missing.error
    assert matched.is_succeeded is True
    assert matched.parsed_rows == 1


# 固定辦法頁不需要偽造刊登日期，也必須建立穩定公告供 revision 追蹤。
def test_fixed_page_creates_trackable_notice_without_listing_date() -> None:
    program = ScholarshipProgramWatch(
        "fixed",
        "青力親為服務學習獎勵計畫",
        "測試基金會",
        ("青力親為服務學習獎勵計畫",),
        "https://foundation.example/rules",
        "verified",
        ProgramSourceType.FIXED_PAGE,
    )

    extraction = _extract_program_source_diagnostics(
        "<main><h1>青力親為服務學習獎勵計畫</h1><p>每學期接受申請。</p></main>",
        program.official_url,
        (program,),
    )

    assert len(extraction.records) == 1
    assert extraction.records[0].published_date == ""
    assert extraction.records[0].source_url == program.official_url
    assert extraction.records[0].category == "other"
    assert extraction.program_counts[0].parsed_rows == 1


# HTTP 成功但沒有命中方案別名時，語意狀態必須降級。
def test_semantic_target_rejects_http_only_success() -> None:
    page = ListingPage("https://foundation.example/news", "<html>一般消息</html>")
    crawl = ListingCrawlResult(
        (page,),
        1,
        1,
        1,
        "complete",
        "all_detected_pages_completed",
        tuple(),
    )

    completeness, error = _semantic_target_status(crawl, 0, 0)

    assert completeness == "partial"
    assert error == "入口可連線但未命中方案別名"


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
        successful_programs=30,
        fallback_used=True,
    )

    assert diagnostic.completeness == "partial"
    assert diagnostic.pages_detected == 4
    assert diagnostic.pages_requested == 3
    assert diagnostic.pages_succeeded == 2
    assert diagnostic.rejected_rows == 3
    assert diagnostic.child_sources_succeeded == 30
    assert diagnostic.ssl_compatibility_fallback is True
    assert "parallel_fetch_errors" in diagnostic.error
    assert "page/2" in diagnostic.error
    assert "timeout" in diagnostic.error


# 正規化後少於四字的短別名不得單獨觸發方案命中。
def test_short_alias_is_ignored() -> None:
    program = ScholarshipProgramWatch(
        "short",
        "人工智慧人才獎學金",
        "測試基金會",
        ("AI",),
        "https://foundation.example/news",
        "verified",
    )
    html = """
    <ul>
      <li><span>2026/09/15</span><a href="/news/88">AI 人才活動公告</a></li>
    </ul>
    """

    records, matched = _extract_program_notices(
        html,
        "https://foundation.example/news",
        (program,),
    )

    assert matched == 0
    assert records == []


# 公告連結有實質標題時，不得因同一容器的延伸文字誤命中方案。
def test_link_title_has_priority_over_container_noise() -> None:
    program = _program("energy", "能源工程獎學金")
    html = """
    <ul>
      <li>
        <span>2026/09/15</span>
        <a href="/news/88">一般校園活動公告</a>
        <p>延伸閱讀：能源工程獎學金</p>
      </li>
    </ul>
    """

    records, matched = _extract_program_notices(
        html,
        "https://foundation.example/news",
        (program,),
    )

    assert matched == 0
    assert records == []


# 分享按鈕不得取代同一公告列中的真正公告連結。
def test_share_link_is_ignored_in_favor_of_notice_link() -> None:
    program = _program("energy", "能源工程獎學金")
    html = """
    <ul>
      <li>
        <span>2026/09/15</span>
        <a href="https://www.addtoany.com/share">分享</a>
        <a href="/news/88">能源工程獎學金開放申請</a>
      </li>
    </ul>
    """

    records, matched = _extract_program_notices(
        html,
        "https://foundation.example/news",
        (program,),
    )

    assert matched >= 1
    assert len(records) == 1
    assert records[0].source_url == "https://foundation.example/news/88"


# 同一來源與 URL 即使頁面列出不同日期，仍是同一公告身分。
def test_append_unique_deduplicates_same_announcement_identity() -> None:
    current = Scholarship.from_raw(
        "tun-program-energy",
        "能源工程獎學金開放申請",
        "2026-09-15",
        "https://foundation.example/news/88",
    )
    older = Scholarship.from_raw(
        "tun-program-energy",
        "能源工程獎學金開放申請",
        "2026-08-15",
        "https://foundation.example/news/88",
    )
    records: list[Scholarship] = []
    seen: set[str] = set()

    duplicate_rows = _append_unique(records, seen, [current, older])

    assert duplicate_rows == 1
    assert records == [current]


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
