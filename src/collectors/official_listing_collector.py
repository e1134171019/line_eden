# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import date
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship


DATE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"),
    re.compile(r"(?P<year>1\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"),
)


@dataclass(frozen=True)
class OfficialSourceConfig:
    source_name: str
    source_url: str
    allowed_path_markers: tuple[str, ...]
    row_selector: str = "tr, li, article, .item, .news, .list-item"
    display_name: str = ""


class OfficialListingCollector(BaseCollector):
    """解析官方公告列表中的標題、日期與站內連結。"""

    def __init__(
        self,
        config: OfficialSourceConfig,
        timeout_seconds: float,
        user_agent: str,
    ) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    @property
    def source_label(self) -> str:
        return self.config.display_name or self.config.source_name

    def collect(self) -> list[Scholarship]:
        html = self._fetch_html()
        return self._parse_html(html)

    def _fetch_html(self) -> str:
        response = httpx.get(
            self.config.source_url,
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.text

    def _parse_html(self, html: str) -> list[Scholarship]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        seen_urls: set[str] = set()
        for container in soup.select(self.config.row_selector):
            text = container.get_text(" ", strip=True)
            link = container.find("a", href=True)
            if link is None:
                continue
            title = link.get_text(" ", strip=True)
            url = urljoin(self.config.source_url, link.get("href", ""))
            if not self._is_allowed_url(url) or not _looks_relevant(title):
                continue
            published_date = _extract_date(text)
            if not published_date:
                continue
            if url in seen_urls:
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
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        year = int(match.group("year"))
        if year < 1911:
            year += 1911
        try:
            return date(year, int(match.group("month")), int(match.group("day"))).isoformat()
        except ValueError:
            continue
    return ""


def _looks_relevant(title: str) -> bool:
    normalized = " ".join(title.split())
    if len(normalized) < 4:
        return False
    return any(keyword in normalized for keyword in ("獎學金", "助學金", "獎助", "補助", "就學金"))
