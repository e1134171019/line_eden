# -*- coding: utf-8 -*-

from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectionMode, CollectorDiagnostic
from src.collectors.helpdreams_collector import HelpDreamsCollector
from src.collectors.http_client import SafeHttpClient
from src.collectors.indigenous_grant_collector import IndigenousGrantCollector
from src.collectors.listing_paginator import crawl_listing_pages
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

    # 由共用 paginator 抓取入口頁或完整歷史分頁，再解析龍華公告列。
    def _collect_lhu(self) -> list[Scholarship]:
        with SafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            result = crawl_listing_pages(
                self.source_url,
                self.collection_mode,
                self.max_pages,
                client.get_text,
                skip_dyna_page_one=True,
            )
            fallback_used = bool(client.fallback_hosts)

        records: list[Scholarship] = []
        seen: set[str] = set()
        raw_rows = 0
        for page in result.pages:
            page_records, page_rows = self._parse_html_with_count(page.html)
            raw_rows += page_rows
            for item in page_records:
                if item.source_url in seen:
                    continue
                seen.add(item.source_url)
                records.append(item)

        error = "; ".join(result.errors)
        self.lhu_diagnostic = CollectorDiagnostic(
            completeness=result.completeness,
            pages_detected=result.pages_detected,
            pages_requested=result.pages_requested,
            pages_succeeded=result.pages_succeeded,
            raw_rows=raw_rows,
            parsed_rows=len(records),
            rejected_rows=max(raw_rows - len(records), 0),
            stop_reason=result.stop_reason,
            error=error,
            ssl_compatibility_fallback=fallback_used,
        )
        if not records and error:
            raise RuntimeError(error)
        return records

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
    def source_url(self) -> str:
        """純函式：提供龍華單站入口供來源口徑統計。"""

        return self.owner.source_url

    @property
    def diagnostic(self) -> CollectorDiagnostic:
        return self.owner.lhu_diagnostic

    def collect(self) -> list[Scholarship]:
        return self.owner._collect_lhu()
