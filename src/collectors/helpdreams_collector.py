# -*- coding: utf-8 -*-

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectorDiagnostic
from src.collectors.http_client import SafeHttpClient
from src.models.scholarship import Scholarship


class HelpDreamsCollector(BaseCollector):
    """解析教育部圓夢助學網單頁資料表，不把截止日冒充公告日期。"""

    def __init__(
        self,
        source_name: str,
        source_label: str,
        source_url: str,
        timeout_seconds: float,
        user_agent: str,
    ) -> None:
        self.source_name = source_name
        self.source_label = source_label
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.diagnostic = CollectorDiagnostic()

    # 下載單頁清單並輸出完整列數診斷。
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

    # 解析獎學金名稱、詳細頁 URL；第三欄只做列驗證，不寫入 published_date。
    def _parse_html_with_count(self, html: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        raw_rows = 0
        seen_urls: set[str] = set()
        for row in soup.select("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            link = cells[0].find("a", href=True)
            if link is None:
                continue
            raw_rows += 1
            href = str(link.get("href", "")).strip()
            title = " ".join(link.get_text(" ", strip=True).split())
            url = urljoin(self.source_url, href)
            if "Grants_Content.aspx" not in url or not title or url in seen_urls:
                continue
            seen_urls.add(url)
            records.append(Scholarship.from_raw(self.source_name, title, "", url))
        return records, raw_rows

    # 保留既有測試與人工診斷可直接解析 HTML。
    def _parse_html(self, html: str) -> list[Scholarship]:
        records, _ = self._parse_html_with_count(html)
        return records
