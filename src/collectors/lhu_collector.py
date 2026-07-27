# -*- coding: utf-8 -*-

from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from src.collectors.base_collector import BaseCollector
from src.collectors.multi_source_collector import MultiSourceCollector
from src.collectors.official_listing_collector import (
    OfficialListingCollector,
    OfficialSourceConfig,
)
from src.models.scholarship import Scholarship


OFFICIAL_SOURCE_CONFIGS = (
    OfficialSourceConfig(
        "moe-helpdreams-private",
        "https://www.edu.tw/helpdreams/Grants.aspx?n=2BBF7170197CE7D3&sms=0A01A72AAB9E5CD4",
        ("Grants_Content.aspx",),
    ),
    OfficialSourceConfig(
        "moe-helpdreams-government",
        "https://www.edu.tw/helpdreams/Grants.aspx?n=11EFF33070D6DF4B&sms=931FF851D2FB2128",
        ("Grants_Content.aspx",),
    ),
    OfficialSourceConfig(
        "indigenous-grants",
        "https://cipgrant.fju.edu.tw/news",
        ("/news/view/",),
    ),
    OfficialSourceConfig(
        "moe-overseas-scholarships",
        "https://www.scholarship.moe.gov.tw/",
        ("/scholarship", "/eu/", "/top100/", "/studyabroad/"),
        "article, li, .item, .news, .card, .list-group-item",
    ),
)


class LhuCollector(BaseCollector):
    """五個官方來源的入口；保留舊類別名稱以維持相容性。"""

    def __init__(self, source_url: str, timeout_seconds: float, user_agent: str) -> None:
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.multi_source: MultiSourceCollector | None = None

    def collect(self) -> list[Scholarship]:
        collectors: list[BaseCollector] = [_LhuOnlyCollector(self)]
        collectors.extend(
            OfficialListingCollector(config, self.timeout_seconds, self.user_agent)
            for config in OFFICIAL_SOURCE_CONFIGS
        )
        self.multi_source = MultiSourceCollector(collectors)
        return self.multi_source.collect()

    def _collect_lhu(self) -> list[Scholarship]:
        return self._parse_html(self._fetch_html())

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

    def _parse_html(self, html: str) -> list[Scholarship]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        for row in soup.select("tr"):
            scholarship = self._parse_row(row)
            if scholarship is not None:
                records.append(scholarship)
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
        href = link.get("href", "").strip() if link else ""
        source_url = urljoin(self.source_url, href) if href else self.source_url
        return Scholarship.from_raw("lhu", title, date_text, source_url)

    def _is_date(self, value: str) -> bool:
        try:
            datetime.strptime(value.strip(), "%Y-%m-%d")
            return True
        except ValueError:
            return False


class _LhuOnlyCollector(BaseCollector):
    """避免 MultiSourceCollector 再次呼叫五來源入口。"""

    def __init__(self, owner: LhuCollector) -> None:
        self.owner = owner

    def collect(self) -> list[Scholarship]:
        return self.owner._collect_lhu()
