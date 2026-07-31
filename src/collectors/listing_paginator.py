# -*- coding: utf-8 -*-

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256

from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.listing_utils import (
    detect_total_pages,
    dyna_page_urls,
    next_page_url,
    numbered_page_urls,
)


@dataclass(frozen=True)
class ListingPage:
    """一個成功取得的公告列表頁。"""

    url: str
    html: str


@dataclass(frozen=True)
class ListingCrawlResult:
    """單一入口的分頁完整性與成功頁面。"""

    pages: tuple[ListingPage, ...]
    pages_detected: int
    pages_requested: int
    pages_succeeded: int
    completeness: str
    stop_reason: str
    errors: tuple[str, ...]


# 依執行模式抓第一頁或遍歷自動偵測到的列表分頁。
def crawl_listing_pages(
    entry_url: str,
    collection_mode: CollectionMode,
    max_pages: int,
    fetch_text: Callable[[str], str],
) -> ListingCrawlResult:
    queue: deque[str] = deque([entry_url])
    visited: set[str] = set()
    fingerprints: set[str] = set()
    pages: list[ListingPage] = []
    errors: list[str] = []
    detected = 1
    requested = 0
    stop_reason = ""

    while queue and requested < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        requested += 1
        try:
            html = fetch_text(url)
        except Exception as error:
            errors.append(f"{url}（{_error_text(error)}）")
            visited.add(url)
            continue
        visited.add(url)
        fingerprint = sha256(html.encode("utf-8")).hexdigest()
        if fingerprint in fingerprints:
            stop_reason = "page_content_loop_detected"
            break
        fingerprints.add(fingerprint)
        pages.append(ListingPage(url, html))
        detected = max(detected, detect_total_pages(html), len(visited))
        if collection_mode is CollectionMode.INCREMENTAL:
            stop_reason = "incremental_first_page"
            break
        _enqueue_pages(queue, visited, html, url)

    if not stop_reason:
        stop_reason = _final_stop_reason(queue, errors)
    completeness = _completeness(
        collection_mode,
        detected,
        len(pages),
        stop_reason,
        errors,
    )
    return ListingCrawlResult(
        tuple(pages),
        detected,
        requested,
        len(pages),
        completeness,
        stop_reason,
        tuple(errors),
    )


# 將 DYNA、數字頁碼及下一頁加入待抓佇列。
def _enqueue_pages(
    queue: deque[str],
    visited: set[str],
    html: str,
    current_url: str,
) -> None:
    candidates = [
        *(url for _, url in dyna_page_urls(html, current_url)),
        *(url for _, url in numbered_page_urls(html, current_url)),
    ]
    next_url = next_page_url(html, current_url)
    if next_url:
        candidates.append(next_url)
    for url in candidates:
        if url not in visited and url not in queue:
            queue.append(url)


# 根據是否仍有待抓頁面與錯誤決定停止原因。
def _final_stop_reason(queue: deque[str], errors: list[str]) -> str:
    if queue:
        return "max_page_limit"
    if errors:
        return "pagination_exhausted_with_errors"
    return "all_detected_pages_completed"


# 完整稽核有缺頁、循環或頁數上限時只能標記 partial。
def _completeness(
    mode: CollectionMode,
    detected: int,
    succeeded: int,
    stop_reason: str,
    errors: list[str],
) -> str:
    if mode is CollectionMode.INCREMENTAL:
        return "incremental" if succeeded else "failed"
    if errors or stop_reason in {
        "max_page_limit",
        "page_content_loop_detected",
        "pagination_exhausted_with_errors",
    }:
        return "partial"
    return "complete" if succeeded >= detected else "partial"


def _error_text(error: Exception) -> str:
    return " ".join(str(error).split())[:120] or type(error).__name__
