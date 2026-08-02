# -*- coding: utf-8 -*-

from src.catalogs.runtime_program_sources import runtime_resolved_programs
from src.catalogs.tun_program_sources import ResolvedProgramSource
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.listing_paginator import ListingCrawlResult, ListingPage
from src.collectors.resilient_tun_program_watch_collector import (
    ResilientTunProgramWatchCollector,
    _crawl_with_fallback,
)
from src.collectors.tun_program_watch_collector import _ProgramPageFetcher


def _program(program_id: str) -> ResolvedProgramSource:
    return next(
        item for item in runtime_resolved_programs() if item.program_id == program_id
    )


def _failed(url: str) -> ListingCrawlResult:
    return ListingCrawlResult(
        tuple(),
        1,
        1,
        0,
        "partial",
        "entry_fetch_failed",
        (f"{url}（TLS failure）",),
    )


def _success(url: str, html: str = "<html><h1>方案公告</h1></html>") -> ListingCrawlResult:
    return ListingCrawlResult(
        (ListingPage(url, html),),
        1,
        1,
        1,
        "complete",
        "all_detected_pages_completed",
        tuple(),
    )


# 主入口完全抓不到時，必須依序改用人工核對的 fallback。
def test_primary_failure_uses_first_successful_fallback(monkeypatch) -> None:
    program = _program("yonglin-hope")
    expected = program.fallback_urls[0]

    def fake_crawl(url, *_args, **_kwargs):
        return _success(url) if url == expected else _failed(url)

    monkeypatch.setattr(
        "src.collectors.resilient_tun_program_watch_collector.crawl_listing_pages",
        fake_crawl,
    )
    fetcher = _ProgramPageFetcher(10, "test-agent", 1)
    entry_url, crawl, attempts = _crawl_with_fallback(
        (program,),
        CollectionMode.FULL_AUDIT,
        5,
        fetcher,
    )

    assert entry_url == expected
    assert crawl.pages
    assert len(attempts) == 2
    assert attempts[0][0] == program.official_url


# 所有來源都失敗時，診斷必須保留每一個嘗試過的 URL。
def test_all_failed_sources_keep_all_errors(monkeypatch) -> None:
    program = _program("sunshine-wanzu")

    def fake_crawl(url, *_args, **_kwargs):
        return _failed(url)

    monkeypatch.setattr(
        "src.collectors.resilient_tun_program_watch_collector.crawl_listing_pages",
        fake_crawl,
    )
    fetcher = _ProgramPageFetcher(10, "test-agent", 1)
    _, crawl, attempts = _crawl_with_fallback(
        (program,),
        CollectionMode.FULL_AUDIT,
        5,
        fetcher,
    )

    assert not crawl.pages
    assert len(attempts) == 1 + len(program.fallback_urls)
    error_text = "｜".join(crawl.errors)
    assert program.official_url in error_text
    assert all(url in error_text for url in program.fallback_urls)


# 完整 collect 必須將 fallback 頁轉成候選，並保存實際入口與失敗軌跡。
def test_collect_emits_record_and_effective_entry(monkeypatch) -> None:
    program = _program("tf4dr-aid")
    fallback_url = "https://relay.example/tf4dr"
    html = """
    <article>
      <time datetime="2026-02-05"></time>
      <a href="/posts/240">本會114學年度第2學期「助學金」受理申請</a>
    </article>
    """
    failed = _failed(program.official_url)
    success = _success(fallback_url, html)

    monkeypatch.setattr(
        "src.collectors.resilient_tun_program_watch_collector.runtime_resolved_programs",
        lambda: (program,),
    )
    monkeypatch.setattr(
        "src.collectors.resilient_tun_program_watch_collector.runtime_monitorable_programs",
        lambda: (program,),
    )
    monkeypatch.setattr(
        "src.collectors.resilient_tun_program_watch_collector._crawl_with_fallback",
        lambda *_args: (
            fallback_url,
            success,
            ((program.official_url, failed), (fallback_url, success)),
        ),
    )

    collector = ResilientTunProgramWatchCollector(
        10,
        "test-agent",
        CollectionMode.FULL_AUDIT,
        5,
        1,
    )
    records = collector.collect()

    assert records
    assert {item.program_id for item in records} == {"tf4dr-aid"}
    assert all(item.entry_url == fallback_url for item in records)
    assert collector.program_states[0].status == "matched"
    assert collector.program_states[0].entry_url == fallback_url
    assert "主入口失敗後改用 fallback" in collector.program_states[0].reason
