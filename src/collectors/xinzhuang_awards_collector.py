# -*- coding: utf-8 -*-

from collections import deque
from datetime import date
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectionMode, CollectorDiagnostic
from src.collectors.http_client import SafeHttpClient
from src.collectors.listing_utils import (
    detect_total_pages,
    extract_date,
    next_page_url,
    numbered_page_urls,
)
from src.models.scholarship import Scholarship

_DETAIL_PATH_MARKER = "/Schs/Frontend/RowContent"
_CHINESE_DATE_PATTERN = re.compile(
    r"(?P<year>\d{3,4})年\s*(?P<month>\d{1,2})月\s*(?P<day>\d{1,2})日"
)


class XinzhuangAwardsCollector(BaseCollector):
    """抓取新莊區聯合獎助學金訊息專區及其分頁公告。"""

    source_label = "新北市新莊區聯合獎助學金"

    def __init__(
        self,
        source_url: str,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode,
        max_pages: int,
    ) -> None:
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.collection_mode = collection_mode
        self.max_pages = max_pages
        self.diagnostic = CollectorDiagnostic()

    # 完整稽核跟隨頁碼；每日增量只讀最新入口頁。
    def collect(self) -> list[Scholarship]:
        queue: deque[str] = deque([self.source_url])
        visited: set[str] = set()
        seen_urls: set[str] = set()
        records: list[Scholarship] = []
        pages_requested = 0
        raw_rows = 0
        detected = 1
        stop_reason = ""
        error = ""
        fallback_used = False
        with SafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            while queue and pages_requested < self.max_pages:
                url = queue.popleft()
                if url in visited:
                    continue
                pages_requested += 1
                try:
                    html = client.get_text(url)
                except Exception as page_error:
                    error = " ".join(str(page_error).split())[:180]
                    stop_reason = "page_fetch_failed"
                    break
                visited.add(url)
                page_records, page_rows = self._parse_html_with_count(html, url)
                raw_rows += page_rows
                new_records = [
                    item for item in page_records if item.source_url not in seen_urls
                ]
                for item in new_records:
                    seen_urls.add(item.source_url)
                records.extend(new_records)
                detected = max(detected, detect_total_pages(html), len(visited))
                if self.collection_mode is CollectionMode.INCREMENTAL:
                    stop_reason = "incremental_first_page"
                    break
                if page_records and not new_records:
                    stop_reason = "record_page_loop_detected"
                    break
                self._enqueue_pages(queue, visited, html, url)
                if len(visited) >= detected and not queue:
                    stop_reason = "all_detected_pages_completed"
                    break
            fallback_used = bool(client.fallback_hosts)
        if not stop_reason:
            stop_reason = "max_page_limit" if queue else "pagination_exhausted"
        completeness = self._completeness(
            detected,
            len(visited),
            bool(records),
            error,
            stop_reason,
        )
        self.diagnostic = CollectorDiagnostic(
            completeness=completeness,
            pages_detected=detected,
            pages_requested=pages_requested,
            pages_succeeded=len(visited),
            raw_rows=raw_rows,
            parsed_rows=len(records),
            rejected_rows=max(raw_rows - len(records), 0),
            stop_reason=stop_reason,
            error=error,
            ssl_compatibility_fallback=fallback_used,
        )
        if not records and error:
            raise RuntimeError(error)
        return records

    # 僅跟隨同一訊息列表的數字頁碼及下一頁。
    def _enqueue_pages(
        self,
        queue: deque[str],
        visited: set[str],
        html: str,
        current_url: str,
    ) -> None:
        for _, url in numbered_page_urls(html, current_url):
            if url not in visited and url not in queue:
                queue.append(url)
        next_url = next_page_url(html, current_url)
        if next_url and next_url not in visited and next_url not in queue:
            queue.append(next_url)

    # 以 RowContent 詳情連結識別正式公告，避免導覽連結混入。
    def _parse_html_with_count(
        self,
        html: str,
        page_url: str | None = None,
    ) -> tuple[list[Scholarship], int]:
        base_url = page_url or self.source_url
        soup = BeautifulSoup(html, "html.parser")
        links = [
            link
            for link in soup.find_all("a", href=True)
            if self._is_detail_link(link, base_url)
        ]
        records: list[Scholarship] = []
        seen_urls: set[str] = set()
        for link in links:
            title = " ".join(link.get_text(" ", strip=True).split())
            source_url = urljoin(base_url, str(link.get("href", "")))
            if not title or source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            records.append(
                Scholarship.from_raw(
                    "ntpc-xinzhuang-awards",
                    title,
                    self._date_near_link(link),
                    source_url,
                )
            )
        return records, len(links)

    def _parse_html(self, html: str) -> list[Scholarship]:
        records, _ = self._parse_html_with_count(html)
        return records

    # 確認連結仍位於同一主機且指向公告詳情頁。
    def _is_detail_link(self, link: Tag, base_url: str) -> bool:
        candidate = urljoin(base_url, str(link.get("href", "")))
        parsed = urlparse(candidate)
        return (
            parsed.hostname == urlparse(base_url).hostname
            and _DETAIL_PATH_MARKER.casefold() in parsed.path.casefold()
        )

    # 優先從表格列取得發布日期，再向上搜尋附近容器。
    def _date_near_link(self, link: Tag) -> str:
        row = link.find_parent("tr")
        if row is not None:
            value = self._extract_date(row.get_text(" ", strip=True))
            if value:
                return value
        current: Tag | None = link
        for _ in range(5):
            parent = current.parent if current is not None else None
            current = parent if isinstance(parent, Tag) else None
            if current is None:
                break
            value = self._extract_date(current.get_text(" ", strip=True))
            if value:
                return value
        return ""

    # 支援西元與民國「年／月／日」格式，統一輸出 ISO 日期。
    def _extract_date(self, text: str) -> str:
        normalized = extract_date(text)
        if normalized:
            return normalized
        match = _CHINESE_DATE_PATTERN.search(text)
        if match is None:
            return ""
        year = int(match.group("year"))
        if year < 1911:
            year += 1911
        try:
            return date(
                year,
                int(match.group("month")),
                int(match.group("day")),
            ).isoformat()
        except ValueError:
            return ""

    # 來源有資料且所有偵測頁成功時才標示完整。
    def _completeness(
        self,
        detected: int,
        succeeded: int,
        has_records: bool,
        error: str,
        stop_reason: str,
    ) -> str:
        if self.collection_mode is CollectionMode.INCREMENTAL:
            return "incremental"
        if (
            error
            or not has_records
            or stop_reason in {"record_page_loop_detected", "max_page_limit"}
        ):
            return "partial"
        return "complete" if succeeded >= detected else "partial"
