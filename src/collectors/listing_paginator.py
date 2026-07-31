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

BatchFetch = Callable[
    [tuple[str, ...]],
    tuple[dict[str, str], dict[str, str]],
]


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


# 先抓入口頁；可完整列出頁碼時批次抓取，否則退回循序追蹤 next。
def crawl_listing_pages(
    entry_url: str,
    collection_mode: CollectionMode,
    max_pages: int,
    fetch_text: Callable[[str], str],
    fetch_many: BatchFetch | None = None,
) -> ListingCrawlResult:
    try:
        entry_html = fetch_text(entry_url)
    except Exception as error:
        message = f"{entry_url}（{_error_text(error)}）"
        return _result(tuple(), 1, 1, (message,), "entry_fetch_failed", collection_mode)

    entry_page = ListingPage(entry_url, entry_html)
    detected = detect_total_pages(entry_html, entry_url)
    if collection_mode is CollectionMode.INCREMENTAL:
        return _result(
            (entry_page,),
            detected,
            1,
            tuple(),
            "incremental_first_page",
            collection_mode,
        )

    known_urls = _known_page_urls(entry_html, entry_url, max_pages)
    if fetch_many and _known_pages_are_complete(detected, known_urls, max_pages):
        return _crawl_known_pages(
            entry_page,
            detected,
            known_urls,
            fetch_many,
            collection_mode,
            max_pages,
        )
    return _crawl_sequential(
        entry_page,
        detected,
        known_urls,
        collection_mode,
        max_pages,
        fetch_text,
    )


# 首頁已列出完整頁碼時，以有限併發下載其餘頁面並保留原順序。
def _crawl_known_pages(
    entry_page: ListingPage,
    detected: int,
    known_urls: tuple[str, ...],
    fetch_many: BatchFetch,
    mode: CollectionMode,
    max_pages: int,
) -> ListingCrawlResult:
    pages_by_url, errors_by_url = fetch_many(known_urls)
    pages = [entry_page]
    fingerprints = {sha256(entry_page.html.encode("utf-8")).hexdigest()}
    duplicate_content = False
    for url in known_urls:
        html = pages_by_url.get(url)
        if html is None:
            continue
        fingerprint = sha256(html.encode("utf-8")).hexdigest()
        if fingerprint in fingerprints:
            duplicate_content = True
            continue
        fingerprints.add(fingerprint)
        pages.append(ListingPage(url, html))
    errors = tuple(f"{url}（{message}）" for url, message in errors_by_url.items())
    limited = detected > max_pages
    stop_reason = _parallel_stop_reason(errors, duplicate_content, limited)
    return _result(
        tuple(pages),
        detected,
        1 + len(known_urls),
        errors,
        stop_reason,
        mode,
    )


# 頁碼無法一次列全時，延續既有 queue 策略逐頁發現後續頁面。
def _crawl_sequential(
    entry_page: ListingPage,
    detected: int,
    known_urls: tuple[str, ...],
    mode: CollectionMode,
    max_pages: int,
    fetch_text: Callable[[str], str],
) -> ListingCrawlResult:
    queue: deque[str] = deque(known_urls)
    visited = {entry_page.url}
    fingerprints = {sha256(entry_page.html.encode("utf-8")).hexdigest()}
    pages = [entry_page]
    errors: list[str] = []
    requested = 1
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
        detected = max(detected, detect_total_pages(html, url), len(visited))
        _enqueue_pages(queue, visited, html, url, max_pages)

    if not stop_reason:
        stop_reason = _final_stop_reason(queue, errors)
    return _result(tuple(pages), detected, requested, tuple(errors), stop_reason, mode)


# 取得入口頁已明確列出的 DYNA、數字頁碼與下一頁，並套用頁數上限。
def _known_page_urls(html: str, current_url: str, max_pages: int) -> tuple[str, ...]:
    candidates = [
        *(url for _, url in dyna_page_urls(html, current_url)),
        *(url for _, url in numbered_page_urls(html, current_url)),
    ]
    next_url = next_page_url(html, current_url)
    if next_url:
        candidates.append(next_url)
    return tuple(dict.fromkeys(url for url in candidates if url != current_url))[: max_pages - 1]


# 只有已知網址覆蓋所有偵測頁面時才使用批次，避免遺漏 next-only 分頁。
def _known_pages_are_complete(
    detected: int,
    known_urls: tuple[str, ...],
    max_pages: int,
) -> bool:
    expected = min(detected, max_pages)
    return expected > 1 and len(known_urls) + 1 >= expected


# 將後續發現的分頁加入佇列，避免待抓網址無限制膨脹。
def _enqueue_pages(
    queue: deque[str],
    visited: set[str],
    html: str,
    current_url: str,
    max_pages: int,
) -> None:
    for url in _known_page_urls(html, current_url, max_pages):
        if len(queue) + len(visited) >= max_pages:
            break
        if url not in visited and url not in queue:
            queue.append(url)


# 併發模式的停止原因必須反映錯誤、內容循環或頁數上限。
def _parallel_stop_reason(
    errors: tuple[str, ...],
    duplicate_content: bool,
    limited: bool,
) -> str:
    if errors:
        return "parallel_fetch_errors"
    if duplicate_content:
        return "page_content_loop_detected"
    if limited:
        return "max_page_limit"
    return "all_detected_pages_completed"


# 根據是否仍有待抓頁面與錯誤決定循序模式停止原因。
def _final_stop_reason(queue: deque[str], errors: list[str]) -> str:
    if queue:
        return "max_page_limit"
    if errors:
        return "pagination_exhausted_with_errors"
    return "all_detected_pages_completed"


# 統一建立結果並依頁數、停止原因與錯誤判定完整性。
def _result(
    pages: tuple[ListingPage, ...],
    detected: int,
    requested: int,
    errors: tuple[str, ...],
    stop_reason: str,
    mode: CollectionMode,
) -> ListingCrawlResult:
    completeness = _completeness(mode, detected, len(pages), stop_reason, errors)
    return ListingCrawlResult(
        pages,
        detected,
        requested,
        len(pages),
        completeness,
        stop_reason,
        errors,
    )


# 完整稽核有缺頁、循環、併發錯誤或頁數上限時只能標記 partial。
def _completeness(
    mode: CollectionMode,
    detected: int,
    succeeded: int,
    stop_reason: str,
    errors: tuple[str, ...],
) -> str:
    if mode is CollectionMode.INCREMENTAL:
        return "incremental" if succeeded else "failed"
    incomplete_reasons = {
        "entry_fetch_failed",
        "max_page_limit",
        "page_content_loop_detected",
        "pagination_exhausted_with_errors",
        "parallel_fetch_errors",
    }
    if errors or stop_reason in incomplete_reasons:
        return "partial"
    return "complete" if succeeded >= detected else "partial"


def _error_text(error: Exception) -> str:
    return " ".join(str(error).split())[:120] or type(error).__name__
