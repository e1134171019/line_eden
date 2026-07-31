# -*- coding: utf-8 -*-

from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectorDiagnostic
from src.collectors.http_client import SafeHttpClient
from src.collectors.listing_utils import extract_date
from src.models.scholarship import Scholarship


class IndigenousGrantCollector(BaseCollector):
    """解析原民會獎助學金網站全部最新消息，不用關鍵字提前砍資料。"""

    source_label = "原住民族委員會大專校院獎助學金"

    def __init__(self, source_url: str, timeout_seconds: float, user_agent: str) -> None:
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.diagnostic = CollectorDiagnostic()

    # 下載最新消息單頁並保留每一則 /news/view/ 公告。
    def collect(self) -> list[Scholarship]:
        with SafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            html = client.get_text(self.source_url)
            records, raw_rows = self._parse_html_with_count(html)
            self.diagnostic = CollectorDiagnostic(
                completeness="complete",
                pages_detected=1,
                pages_requested=1,
                pages_succeeded=1,
                raw_rows=raw_rows,
                parsed_rows=len(records),
                rejected_rows=max(raw_rows - len(records), 0),
                stop_reason="single_page_completed",
                ssl_compatibility_fallback=bool(client.fallback_hosts),
            )
            return records

    # 以公告連結為主鍵，日期找不到時仍保留公告並交由後續正文判斷。
    def _parse_html_with_count(self, html: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        seen_urls: set[str] = set()
        links = [
            link
            for link in soup.find_all("a", href=True)
            if "/news/view/" in str(link.get("href", ""))
        ]
        for link in links:
            title = " ".join(link.get_text(" ", strip=True).split())
            url = urljoin(self.source_url, str(link.get("href", "")))
            if not title or url in seen_urls:
                continue
            seen_urls.add(url)
            published_date = self._date_near_link(link)
            records.append(
                Scholarship.from_raw(
                    "indigenous-grants",
                    title,
                    published_date,
                    url,
                )
            )
        return records, len(links)

    # 從最接近的列、卡片或區塊找新聞日期。
    def _date_near_link(self, link: Tag) -> str:
        for parent_name in ("tr", "li", "article", "div"):
            parent = link.find_parent(parent_name)
            if parent is None:
                continue
            value = extract_date(parent.get_text(" ", strip=True))
            if value:
                return value
        return ""

    # 保留測試與稽核可直接解析 fixture。
    def _parse_html(self, html: str) -> list[Scholarship]:
        records, _ = self._parse_html_with_count(html)
        return records
