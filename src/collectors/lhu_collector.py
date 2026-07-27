# -*- coding: utf-8 -*-

from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship


class LhuCollector(BaseCollector):
    """龍華獎助學金公告蒐集器。"""

    # 初始化龍華公告頁抓取設定。
    def __init__(self, source_url: str, timeout_seconds: float, user_agent: str) -> None:
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    # 取得公告頁並解析成 Scholarship 清單。
    def collect(self) -> list[Scholarship]:
        html = self._fetch_html()
        return self._parse_html(html)

    # 以 timeout 與 User-Agent 下載龍華公告頁面。
    def _fetch_html(self) -> str:
        headers = {"User-Agent": self.user_agent}
        response = httpx.get(
            self.source_url,
            headers=headers,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.text

    # 從 HTML 表格擷取日期、標題與公告連結。
    def _parse_html(self, html: str) -> list[Scholarship]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        for row in soup.select("tr"):
            scholarship = self._parse_row(row)
            if scholarship is not None:
                records.append(scholarship)
        return records

    # 解析單列表格列，非公告列時回傳 None。
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
        href = link.get("href", "").strip() if link else ""
        source_url = urljoin(self.source_url, href) if href else self.source_url
        return Scholarship.from_raw("lhu", title, date_text, source_url)

    # 驗證日期是否符合 YYYY-MM-DD。
    def _is_date(self, value: str) -> bool:
        try:
            datetime.strptime(value.strip(), "%Y-%m-%d")
            return True
        except ValueError:
            return False
