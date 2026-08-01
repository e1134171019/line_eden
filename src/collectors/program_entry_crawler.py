# -*- coding: utf-8 -*-

from collections.abc import Callable
from typing import Protocol

from src.catalogs.tun_2025_program_catalog import ProgramSourceType
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.listing_paginator import (
    ListingCrawlResult,
    ListingPage,
    crawl_listing_pages,
)

FetchText = Callable[[str], str]
FetchMany = Callable[
    [tuple[str, ...]],
    tuple[dict[str, str], dict[str, str]],
]


class ProgramEntryCrawler(Protocol):
    """定義不同方案入口共用的下載介面。"""

    def fetch_pages(
        self,
        entry_url: str,
        collection_mode: CollectionMode,
        max_pages: int,
        fetch_text: FetchText,
        fetch_many: FetchMany,
    ) -> ListingCrawlResult: ...


class ListingProgramEntryCrawler:
    """下載會持續新增公告與分頁的列表入口。"""

    def fetch_pages(
        self,
        entry_url: str,
        collection_mode: CollectionMode,
        max_pages: int,
        fetch_text: FetchText,
        fetch_many: FetchMany,
    ) -> ListingCrawlResult:
        return crawl_listing_pages(
            entry_url,
            collection_mode,
            max_pages,
            fetch_text,
            fetch_many,
        )


class SinglePageProgramEntryCrawler:
    """下載以內容修訂代表更新的固定頁或動態入口。"""

    def fetch_pages(
        self,
        entry_url: str,
        collection_mode: CollectionMode,
        max_pages: int,
        fetch_text: FetchText,
        fetch_many: FetchMany,
    ) -> ListingCrawlResult:
        del max_pages, fetch_many
        return _fetch_single_page(entry_url, collection_mode, fetch_text)


def select_program_entry_crawler(source_type: ProgramSourceType) -> ProgramEntryCrawler:
    """純函式：依來源型態選擇可替換的入口下載器。"""

    if source_type is ProgramSourceType.LISTING:
        return ListingProgramEntryCrawler()
    return SinglePageProgramEntryCrawler()


def _fetch_single_page(
    entry_url: str,
    collection_mode: CollectionMode,
    fetch_text: FetchText,
) -> ListingCrawlResult:
    """副作用函式：固定頁只下載一次並保留明確失敗診斷。"""

    try:
        html = fetch_text(entry_url)
    except Exception as error:
        message = f"{entry_url}（{_error_text(error)}）"
        return ListingCrawlResult(
            tuple(), 1, 1, 0, "failed", "entry_fetch_failed", (message,)
        )
    completeness = (
        "incremental" if collection_mode is CollectionMode.INCREMENTAL else "complete"
    )
    page = ListingPage(entry_url, html)
    return ListingCrawlResult(
        (page,), 1, 1, 1, completeness, "single_page_completed", tuple()
    )


def _error_text(error: Exception) -> str:
    """純函式：壓縮入口下載錯誤，避免稽核輸出失控。"""

    return " ".join(str(error).split())[:120] or type(error).__name__
