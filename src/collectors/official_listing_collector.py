# -*- coding: utf-8 -*-

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectorDiagnostic
from src.collectors.http_client import SafeHttpClient
from src.collectors.listing_utils import extract_date
from src.models.scholarship import Scholarship


@dataclass(frozen=True)
class OfficialSourceConfig:
    source_name: str
    source_url: str
    allowed_path_markers: tuple[str, ...]
    row_selector: str = "tr, li, article, .item, .news, .list-item"
    display_name: str = ""


class OfficialListingCollector(BaseCollector):
    """相容舊測試的單頁官方公告解析器；新來源改用專用 collector。"""

    def __init__(
        self,
        config: OfficialSourceConfig,
        timeout_seconds: float,
        user_agent: str,
    ) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.diagnostic = CollectorDiagnostic()

    @property
    def source_label(self) -> str:
        return self.config.display_name or self.config.source_name

    # 下載一頁並回報解析數量。
    def collect(self) -> list[Scholarship]:
        with SafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            html = client.get_text(self.config.source_url)
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

    # 保留可直接呼叫的下載函式。
    def _fetch_html(self) -> str:
        with SafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            return client.get_text(self.config.source_url)

    # 解析候選容器並統計有連結的原始列。
    def _parse_html_with_count(self, html: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        seen_urls: set[str] = set()
        raw_rows = 0
        for container in soup.select(self.config.row_selector):
            link = container.find("a", href=True)
            if link is None:
                continue
            raw_rows += 1
            text = container.get_text(" ", strip=True)
            title = link.get_text(" ", strip=True)
            url = urljoin(self.config.source_url, str(link.get("href", "")))
            if not self._is_allowed_url(url) or not _looks_relevant(title):
                continue
            published_date = extract_date(text)
            if not published_date or url in seen_urls:
                continue
            seen_urls.add(url)
            records.append(
                Scholarship.from_raw(
                    self.config.source_name,
                    title,
                    published_date,
                    url,
                )
            )
        return records, raw_rows

    def _parse_html(self, html: str) -> list[Scholarship]:
        records, _ = self._parse_html_with_count(html)
        return records

    def _is_allowed_url(self, url: str) -> bool:
        parsed = urlparse(url)
        source_host = urlparse(self.config.source_url).netloc
        if parsed.netloc and parsed.netloc != source_host:
            return False
        return any(
            marker in parsed.path or marker in parsed.query
            for marker in self.config.allowed_path_markers
        )


def _extract_date(text: str) -> str:
    """保留舊匯入名稱，實際共用 listing_utils。"""
    return extract_date(text)


def _looks_relevant(title: str) -> bool:
    normalized = " ".join(title.split())
    if len(normalized) < 4:
        return False
    return any(keyword in normalized for keyword in ("獎學金", "助學金", "獎助", "補助", "就學金"))
