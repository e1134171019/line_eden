# -*- coding: utf-8 -*-

from collections import deque
from dataclasses import dataclass
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

_GENERIC_HEADINGS = frozenset({
    "各項公告",
    "申請報名",
    "登入",
    "常見問題",
    "教育部",
    "ministry of education 教育部",
})


@dataclass(frozen=True)
class OverseasChildSource:
    source_name: str
    display_name: str
    list_url: str


OVERSEAS_CHILD_SOURCES = (
    OverseasChildSource(
        "moe-studyabroad",
        "公費留學考試",
        "https://www.scholarship.moe.gov.tw/studyabroad/exam",
    ),
    OverseasChildSource(
        "moe-top100",
        "世界百大合作獎學金",
        "https://www.scholarship.moe.gov.tw/top100/index/index",
    ),
    OverseasChildSource(
        "moe-overseas-scholarship",
        "留學獎學金",
        "https://www.scholarship.moe.gov.tw/scholarship/index/index/page/1",
    ),
    OverseasChildSource(
        "moe-eu-scholarship",
        "教育部歐盟獎學金",
        "https://www.scholarship.moe.gov.tw/eu/index/index",
    ),
)


class MoeOverseasCollector(BaseCollector):
    """分別抓取公費留學、世界百大、留學及歐盟四個公告子站。"""

    source_label = "教育部留學獎學金"

    def __init__(
        self,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode,
        max_pages: int,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.collection_mode = collection_mode
        self.max_pages = max_pages
        self.diagnostic = CollectorDiagnostic(child_sources_detected=4)

    # 逐一執行四個子來源，單一子站失敗不得隱藏其他成功結果。
    def collect(self) -> list[Scholarship]:
        records: list[Scholarship] = []
        diagnostics: list[CollectorDiagnostic] = []
        errors: list[str] = []
        fallback_used = False
        with SafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            for child in OVERSEAS_CHILD_SOURCES:
                try:
                    child_records, child_diagnostic = self._collect_child(client, child)
                except Exception as error:
                    errors.append(f"{child.display_name}: {' '.join(str(error).split())[:180]}")
                    continue
                if child_diagnostic.completeness == "failed":
                    errors.append(f"{child.display_name}: {child_diagnostic.error or '抓取失敗'}")
                    continue
                records.extend(child_records)
                diagnostics.append(child_diagnostic)
            fallback_used = bool(client.fallback_hosts)
        unique = self._deduplicate(records)
        succeeded = len(diagnostics)
        if succeeded == 0:
            self.diagnostic = CollectorDiagnostic(
                completeness="failed",
                error="; ".join(errors),
                child_sources_detected=len(OVERSEAS_CHILD_SOURCES),
                child_sources_succeeded=0,
                ssl_compatibility_fallback=fallback_used,
            )
            raise RuntimeError(f"教育部留學四個子站全部失敗：{'; '.join(errors)}")
        completeness = self._overall_completeness(diagnostics, succeeded)
        self.diagnostic = CollectorDiagnostic(
            completeness=completeness,
            pages_detected=sum(item.pages_detected or 0 for item in diagnostics),
            pages_requested=sum(item.pages_requested for item in diagnostics),
            pages_succeeded=sum(item.pages_succeeded for item in diagnostics),
            raw_rows=sum(item.raw_rows for item in diagnostics),
            parsed_rows=len(unique),
            rejected_rows=sum(item.rejected_rows for item in diagnostics),
            stop_reason=self._overall_stop_reason(completeness),
            error="; ".join(errors),
            ssl_compatibility_fallback=fallback_used,
            child_sources_detected=len(OVERSEAS_CHILD_SOURCES),
            child_sources_succeeded=succeeded,
        )
        return unique

    # 抓取單一子站；完整模式跟隨數字頁碼與 next，增量模式只看首頁。
    def _collect_child(
        self,
        client: SafeHttpClient,
        child: OverseasChildSource,
    ) -> tuple[list[Scholarship], CollectorDiagnostic]:
        queue: deque[str] = deque([child.list_url])
        visited: set[str] = set()
        records: list[Scholarship] = []
        raw_rows = 0
        detected = 1
        error = ""
        while queue and len(visited) < self.max_pages:
            url = queue.popleft()
            if url in visited:
                continue
            try:
                html = client.get_text(url)
            except Exception as page_error:
                error = " ".join(str(page_error).split())[:180]
                break
            visited.add(url)
            page_records, page_rows = self._parse_page(html, child, url)
            records.extend(page_records)
            raw_rows += page_rows
            detected = max(detected, detect_total_pages(html))
            if self.collection_mode is CollectionMode.INCREMENTAL:
                break
            self._enqueue_pages(queue, visited, html, url)
            if len(visited) >= detected and not queue:
                break
        completeness = self._child_completeness(
            detected,
            len(visited),
            error,
            len(records),
        )
        diagnostic = CollectorDiagnostic(
            completeness=completeness,
            pages_detected=detected,
            pages_requested=len(visited) + (1 if error else 0),
            pages_succeeded=len(visited),
            raw_rows=raw_rows,
            parsed_rows=len(records),
            rejected_rows=max(raw_rows - len(records), 0),
            stop_reason=self._child_stop_reason(completeness, len(records)),
            error=error,
        )
        return self._deduplicate(records), diagnostic

    # 將頁面發現的數字分頁及下一頁加入佇列。
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

    # 解析具有日期的公告標題，避免導覽與登入區塊混入。
    def _parse_page(
        self,
        html: str,
        child: OverseasChildSource,
        page_url: str,
    ) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        candidate_count = 0
        seen: set[tuple[str, str, str]] = set()
        for heading in soup.find_all(["h2", "h3", "h4", "h5", "h6"]):
            title = " ".join(heading.get_text(" ", strip=True).split())
            if not self._valid_title(title):
                continue
            container, published_date = self._smallest_dated_container(heading)
            if container is None or not published_date:
                continue
            candidate_count += 1
            url = self._announcement_url(heading, container, page_url)
            key = (title, published_date, url)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                Scholarship.from_raw(child.source_name, title, published_date, url)
            )
        return records, candidate_count

    # 由近到遠尋找同時包含標題及日期的最小區塊。
    def _smallest_dated_container(self, heading: Tag) -> tuple[Tag | None, str]:
        current: Tag | None = heading
        for _ in range(5):
            if current is None:
                break
            published_date = extract_date(current.get_text(" ", strip=True))
            if published_date:
                return current, published_date
            parent = current.parent
            current = parent if isinstance(parent, Tag) else None
        return None, ""

    # 優先使用標題自身或最小日期區塊中的站內連結。
    def _announcement_url(self, heading: Tag, container: Tag, page_url: str) -> str:
        link = heading.find("a", href=True)
        if link is None:
            parent_link = heading.find_parent("a", href=True)
            link = parent_link if isinstance(parent_link, Tag) else None
        if link is None:
            link = container.find("a", href=True)
        if link is None:
            return page_url
        candidate = urljoin(page_url, str(link.get("href", "")))
        return candidate if urlparse(candidate).hostname == urlparse(page_url).hostname else page_url

    # 排除網站固定標題與過短導覽文字。
    def _valid_title(self, title: str) -> bool:
        normalized = title.casefold()
        return len(title) >= 4 and normalized not in _GENERIC_HEADINGS

    # 依頁面宣告數、錯誤及解析結果決定子站完整性。
    def _child_completeness(
        self,
        detected: int,
        succeeded: int,
        error: str,
        parsed_count: int,
    ) -> str:
        if error:
            return "partial" if succeeded else "failed"
        if parsed_count == 0:
            return "partial"
        if self.collection_mode is CollectionMode.INCREMENTAL:
            return "incremental"
        return "complete" if succeeded >= detected else "partial"

    # 產生可稽核子站停止原因。
    def _child_stop_reason(self, completeness: str, parsed_count: int) -> str:
        if parsed_count == 0:
            return "no_announcements_parsed"
        if completeness == "incremental":
            return "incremental_first_page"
        if completeness == "complete":
            return "all_detected_pages_completed"
        return "page_fetch_or_pagination_incomplete"

    # 彙整四個子站完整性。
    def _overall_completeness(
        self,
        diagnostics: list[CollectorDiagnostic],
        succeeded: int,
    ) -> str:
        if succeeded != len(OVERSEAS_CHILD_SOURCES):
            return "partial"
        if any(item.completeness == "partial" for item in diagnostics):
            return "partial"
        if self.collection_mode is CollectionMode.INCREMENTAL:
            return "incremental"
        return "complete"

    # 產生聚合來源停止原因。
    def _overall_stop_reason(self, completeness: str) -> str:
        if completeness == "incremental":
            return "all_child_sources_incremental"
        if completeness == "complete":
            return "all_child_sources_completed"
        return "child_source_partial"

    # 依來源、標題、日期及網址移除同站重複公告。
    def _deduplicate(self, records: list[Scholarship]) -> list[Scholarship]:
        result: list[Scholarship] = []
        seen: set[tuple[str, str, str, str]] = set()
        for item in records:
            key = (item.source, item.title, item.published_date, item.source_url)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result
