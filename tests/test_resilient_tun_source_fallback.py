# -*- coding: utf-8 -*-

from src.catalogs.runtime_program_sources import runtime_resolved_programs
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.listing_paginator import ListingCrawlResult, ListingPage
from src.collectors.resilient_tun_program_watch_collector import (
    _crawl_with_fallback,
)
from src.collectors.tun_program_watch_collector import _ProgramPageFetcher


def _program(program_id: str):
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


def _success(url: str) -> ListingCrawlResult:
    return ListingCrawlResult(
        (ListingPage(url, "<html><h1>方案公告</h1></html>"),),
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
