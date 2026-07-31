# -*- coding: utf-8 -*-

from collections import deque
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectionMode, CollectorDiagnostic
from src.collectors.helpdreams_collector import HelpDreamsCollector
from src.collectors.http_client import SafeHttpClient
from src.collectors.indigenous_grant_collector import IndigenousGrantCollector
from src.collectors.listing_utils import (
    detect_total_pages,
    dyna_page_urls,
    next_page_url,
    numbered_page_urls,
)
from src.collectors.moe_overseas_collector import MoeOverseasCollector
from src.collectors.multi_source_collector import MultiSourceCollector
from src.collectors.xinzhuang_awards_collector import XinzhuangAwardsCollector
from src.models.scholarship import Scholarship

_HELPDREAMS_PRIVATE_URL = (
    "https://www.edu.tw/helpdreams/Grants.aspx?"
    "n=2BBF7170197CE7D3&sms=0A01A72AAB9E5CD4"
)
_HELPDREAMS_GOVERNMENT_URL = (
    "https://www.edu.tw/helpdreams/Grants.aspx?"
    "n=11EFF33070D6DF4B&sms=931FF851D2FB2128"
)
_INDIGENOUS_GRANTS_URL = "https://cipgrant.fju.edu.tw/news"
_XINZHUANG_AWARDS_URL = (
    "https://xinzhuangawards.ntpc.gov.tw/Schs/Frontend/RowView?"
    "alias=Cht_News&&id=MjE="
)


class LhuCollector(BaseCollector):
    """六個官方來源入口；完整稽核與每日增量使用不同翻頁策略。"""

    def __init__(
        self,
        source_url: str,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode = CollectionMode.INCREMENTAL,
        max_pages: int = 20,
    ) -> None:
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.collection_mode = collection_mode
        self.max_pages = max_pages
        self.multi_source: MultiSourceCollector | None = None
        self.lhu_diagnostic = CollectorDiagnostic()

    # 建立六個專用來源，不再以單一通用 selector 套全部網站。
    def collect(self) -> list[Scholarship]:
        collectors: list[BaseCollector] = [
            _LhuOnlyCollector(self),
            HelpDreamsCollector(
                "moe-helpdreams-private",
                "教育部圓夢助學網－民間團體",
                _HELPDREAMS_PRIVATE_URL,
                self.timeout_seconds,
                self.user_agent,
            ),
            HelpDreamsCollector(
                "moe-helpdreams-government",
                "教育部圓夢助學網－政府機關",
                _HELPDREAMS_GOVERNMENT_URL,
                self.timeout_seconds,
                self.user_agent,
            ),
            IndigenousGrantCollector(
                _INDIGENOUS_GRANTS_URL,
                self.timeout_seconds,
                self.user_agent,
            ),
            MoeOverseasCollector(
                self.timeout_seconds,
                self.user_agent,
                self.collection_mode,
                self.max_pages,
            ),
            XinzhuangAwardsCollector(
                _XINZHUANG_AWARDS_URL,
                self.timeout_seconds,
                self.user_agent,
                self.collection_mode,
                self.max_pages,
            ),
        ]
        self.multi_source = MultiSourceCollector(collectors)
        return self.multi_source.collect()

    def source_summary_lines(self) -> list[str]:
        if self.multi_source is None:
            return []
        return self.multi_source.summary_lines()

    # 依執行模式抓取第一頁或全部偵測分頁。
    def _collect_lhu(self) -> list[Scholarship]:
        queue: deque[str] = deque([self.source_url])
        visited: set[str] = set()
        seen_records: set[str] = set()
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
                page_records, page_rows = self._parse_html_with_count(html)
                raw_rows += page_rows
                new_records = [
                    item for item in page_records if item.source_url not in seen_records
                ]
                for item in new_records:
                    seen_records.add(item.source_url)
                records.extend(new_records)
                detected = max(detected, detect_total_pages(html), len(visited))
                if self.collection_mode is CollectionMode.INCREMENTAL:
                    stop_reason = "incremental_first_page"
                    break
                if page_records and not new_records:
                    stop_reason = "record_page_loop_detected"
                    break
                self._enqueue_lhu_pages(queue, visited, html, url)
                if len(visited) >= detected and not queue:
                    stop_reason = "all_detected_pages_completed"
                    break
            fallback_used = bool(client.fallback_hosts)
        if not stop_reason:
            stop_reason = "max_page_limit" if queue else "pagination_exhausted"
        completeness = self._lhu_completeness(detected, len(visited), error, stop_reason)
        self.lhu_diagnostic = CollectorDiagnostic(
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

    # 龍華已有 canonical 首頁；後續 DYNA 頁不得再加入第 1 頁別名。
    def _enqueue_lhu_pages(
        self,
        queue: deque[str],
        visited: set[str],
        html: str,
        current_url: str,
    ) -> None:
        dyna_candidates = [
            (page, url)
            for page, url in dyna_page_urls(html, current_url)
            if page != 1
        ]
        candidates = [
            *dyna_candidates,
            *numbered_page_urls(html, current_url),
        ]
        for _, url in candidates:
            if url not in visited and url not in queue:
                queue.append(url)
        next_url = next_page_url(html, current_url)
        if next_url and next_url not in visited and next_url not in queue:
            queue.append(next_url)

    # 完整模式必須成功取得所有偵測頁面，否則只能標示 partial。
    def _lhu_completeness(
        self,
        detected: int,
        succeeded: int,
        error: str,
        stop_reason: str,
    ) -> str:
        if self.collection_mode is CollectionMode.INCREMENTAL:
            return "incremental"
        if error or stop_reason in {"record_page_loop_detected", "max_page_limit"}:
            return "partial"
        return "complete" if succeeded >= detected else "partial"

    # 保留可指定 URL 的下載函式供測試及人工診斷使用。
    def _fetch_html(self, url: str | None = None) -> str:
        with SafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            return client.get_text(url or self.source_url)

    # 解析龍華公告列並回報原始資料列數。
    def _parse_html_with_count(self, html: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        raw_rows = 0
        for row in soup.select("tr"):
            cells = row.find_all("td")
            if cells:
                raw_rows += 1
            scholarship = self._parse_row(row)
            if scholarship is not None:
                records.append(scholarship)
        return records, raw_rows

    def _parse_html(self, html: str) -> list[Scholarship]:
        records, _ = self._parse_html_with_count(html)
        return records

    def _parse_row(self, row: object) -> Scholarship | None:
        cells = getattr(row, "find_all", lambda *_: [])("td")
        if len(cells) < 2:
            return None
        date_text = cells[0].get_text(" ", strip=True)
        if not self._is_date(date_text):
            return None
        link = cells[1].find("a")
        title = link.get_text(" ", strip=True) if link else cells[1].get_text(" ", strip=True)
        if not title:
            return None
        href = str(link.get("href", "")).strip() if link else ""
        source_url = urljoin(self.source_url, href) if href else self.source_url
        return Scholarship.from_raw("lhu", title, date_text, source_url)

    def _is_date(self, value: str) -> bool:
        try:
            datetime.strptime(value.strip(), "%Y-%m-%d")
            return True
        except ValueError:
            return False


class _LhuOnlyCollector(BaseCollector):
    """提供龍華單站給 MultiSourceCollector，避免遞迴建立六來源。"""

    source_label = "龍華科技大學"

    def __init__(self, owner: LhuCollector) -> None:
        self.owner = owner

    @property
    def diagnostic(self) -> CollectorDiagnostic:
        return self.owner.lhu_diagnostic

    def collect(self) -> list[Scholarship]:
        return self.owner._collect_lhu()
