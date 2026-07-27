# -*- coding: utf-8 -*-

from datetime import date
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
import httpx

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship

_DATE_PATTERN = re.compile(
    r"(?P<year>20\d{2}|1\d{2})\s*[年./-]\s*"
    r"(?P<month>\d{1,2})\s*[月./-]\s*(?P<day>\d{1,2})\s*日?"
)


class OfficialAnnouncementCollector(BaseCollector):
    """可設定來源名稱與關鍵字的官方公告清單蒐集器。"""

    def __init__(
        self,
        source_code: str,
        source_name: str,
        source_url: str,
        timeout_seconds: float,
        user_agent: str,
        link_keywords: tuple[str, ...] = (),
        max_records: int = 100,
    ) -> None:
        self.source_code = source_code
        self.source_name = source_name
        self.source_url = source_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.link_keywords = link_keywords
        self.max_records = max_records

    # 下載官方清單頁並轉成統一 Scholarship 格式。
    def collect(self) -> list[Scholarship]:
        return self._parse_html(self._fetch_html())

    def _fetch_html(self) -> str:
        response = httpx.get(
            self.source_url,
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.text

    # 以「有連結、有日期、有公告標題」為最低條件，避免依賴單一網站 CSS。
    def _parse_html(self, html: str) -> list[Scholarship]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        seen_urls: set[str] = set()
        for link in soup.select("a[href]"):
            title = link.get_text(" ", strip=True)
            if not self._is_candidate_title(title):
                continue
            context = self._context_text(link)
            published_date = self._extract_date(context)
            if not published_date:
                continue
            href = str(link.get("href", "")).strip()
            if not href or href.startswith(("javascript:", "mailto:", "#")):
                continue
            source_url = urljoin(self.source_url, href)
            if source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            display_title = self._display_title(title)
            records.append(
                Scholarship.from_raw(
                    self.source_code,
                    display_title,
                    published_date,
                    source_url,
                )
            )
            if len(records) >= self.max_records:
                break
        return records

    def _is_candidate_title(self, title: str) -> bool:
        normalized = " ".join(title.split()).strip()
        if len(normalized) < 4 or len(normalized) > 180:
            return False
        if self.link_keywords and not any(word in normalized for word in self.link_keywords):
            return False
        return True

    def _display_title(self, title: str) -> str:
        normalized = " ".join(title.split()).strip()
        if self.source_name in normalized:
            return normalized
        return f"{self.source_name}｜{normalized}"

    # 往上尋找包含日期與標題的最小區塊，最多三層以免抓到整頁日期。
    def _context_text(self, link: Tag) -> str:
        current: Tag | None = link
        candidates: list[str] = []
        for _ in range(4):
            if current is None:
                break
            text = current.get_text(" ", strip=True)
            if text:
                candidates.append(text)
                if _DATE_PATTERN.search(text):
                    return text
            parent = current.parent
            current = parent if isinstance(parent, Tag) else None
        return " ".join(candidates)

    def _extract_date(self, text: str) -> str:
        match = _DATE_PATTERN.search(text)
        if not match:
            return ""
        year = int(match.group("year"))
        if year < 1911:
            year += 1911
        month = int(match.group("month"))
        day = int(match.group("day"))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""
