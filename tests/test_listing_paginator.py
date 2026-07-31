# -*- coding: utf-8 -*-

from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.listing_paginator import crawl_listing_pages

_ENTRY = "https://example.test/news/page/1"
_PAGE_2 = "https://example.test/news/page/2"
_PAGE_3 = "https://example.test/news/page/3"


def _pages() -> dict[str, str]:
    return {
        _ENTRY: f"""
        <p>第一頁資料</p><p>共3頁</p>
        <a href="{_ENTRY}">1</a>
        <a href="{_PAGE_2}">2</a>
        <a href="{_PAGE_2}" rel="next">下一頁</a>
        """,
        _PAGE_2: f"""
        <p>第二頁資料</p>
        <a href="{_PAGE_3}">3</a>
        <a href="{_PAGE_3}" rel="next">下一頁</a>
        """,
        _PAGE_3: "<p>第三頁資料</p>",
    }


def _all_pages_visible() -> dict[str, str]:
    pages = _pages()
    pages[_ENTRY] = f"""
    <p>第一頁資料</p><p>共3頁</p>
    <a href="{_ENTRY}">1</a>
    <a href="{_PAGE_2}">2</a>
    <a href="{_PAGE_3}">3</a>
    """
    return pages


# 完整稽核必須沿用數字頁碼與下一頁策略抓完所有頁面。
def test_full_audit_follows_all_detected_pages() -> None:
    pages = _pages()

    result = crawl_listing_pages(
        _ENTRY,
        CollectionMode.FULL_AUDIT,
        20,
        lambda url: pages[url],
    )

    assert [page.url for page in result.pages] == [_ENTRY, _PAGE_2, _PAGE_3]
    assert result.pages_detected == 3
    assert result.pages_succeeded == 3
    assert result.completeness == "complete"
    assert result.stop_reason == "all_detected_pages_completed"


# 入口頁列出全部頁碼時，必須一次交給 batch callback 並保留頁碼順序。
def test_known_pages_use_batch_fetch() -> None:
    pages = _all_pages_visible()
    batches: list[tuple[str, ...]] = []

    def fetch_many(urls: tuple[str, ...]) -> tuple[dict[str, str], dict[str, str]]:
        batches.append(urls)
        return ({url: pages[url] for url in reversed(urls)}, {})

    result = crawl_listing_pages(
        _ENTRY,
        CollectionMode.FULL_AUDIT,
        20,
        lambda url: pages[url],
        fetch_many,
    )

    assert batches == [(_PAGE_2, _PAGE_3)]
    assert [page.url for page in result.pages] == [_ENTRY, _PAGE_2, _PAGE_3]
    assert result.pages_requested == 3
    assert result.completeness == "complete"


# 批次下載任一頁失敗時，完整稽核必須標示 partial 並保留錯誤。
def test_batch_failure_is_partial() -> None:
    pages = _all_pages_visible()

    result = crawl_listing_pages(
        _ENTRY,
        CollectionMode.FULL_AUDIT,
        20,
        lambda url: pages[url],
        lambda urls: ({urls[0]: pages[urls[0]]}, {urls[1]: "timeout"}),
    )

    assert result.pages_succeeded == 2
    assert result.completeness == "partial"
    assert result.stop_reason == "parallel_fetch_errors"
    assert "timeout" in result.errors[0]


# 每日增量只抓入口頁，不得呼叫批次或跟進歷史分頁。
def test_incremental_mode_stops_after_entry_page() -> None:
    pages = _all_pages_visible()
    requested: list[str] = []
    batches: list[tuple[str, ...]] = []

    result = crawl_listing_pages(
        _ENTRY,
        CollectionMode.INCREMENTAL,
        20,
        lambda url: requested.append(url) or pages[url],
        lambda urls: batches.append(urls) or ({}, {}),
    )

    assert requested == [_ENTRY]
    assert batches == []
    assert result.pages_succeeded == 1
    assert result.completeness == "incremental"
    assert result.stop_reason == "incremental_first_page"


# 已偵測更多頁但觸及上限時必須標示 partial。
def test_page_limit_is_reported_as_partial() -> None:
    pages = _pages()

    result = crawl_listing_pages(
        _ENTRY,
        CollectionMode.FULL_AUDIT,
        2,
        lambda url: pages[url],
    )

    assert result.pages_succeeded == 2
    assert result.pages_detected == 3
    assert result.completeness == "partial"
    assert result.stop_reason == "max_page_limit"


# 不同分頁網址回傳相同內容時必須停止，避免無限循環。
def test_duplicate_page_content_stops_as_partial() -> None:
    first = f'<p>相同內容</p><a href="{_PAGE_2}" rel="next">下一頁</a>'

    result = crawl_listing_pages(
        _ENTRY,
        CollectionMode.FULL_AUDIT,
        20,
        lambda _: first,
    )

    assert result.pages_succeeded == 1
    assert result.completeness == "partial"
    assert result.stop_reason == "page_content_loop_detected"
