# -*- coding: utf-8 -*-

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
    _extract_date,
    _normalize_text,
)
from src.models.scholarship import Scholarship


class RulingDigitalListScholarshipCollector(AdditionalScholarshipSourceCollector):
    """解析 RulingDigital `/p/403` 列表中的同站 `/p/406` detail links。"""

    def _parse_html(self, html: str, page_url: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        raw_rows = 0

        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag):
                continue
            href = str(anchor.get("href", "")).strip()
            if not href:
                continue
            detail_url = urljoin(page_url, href)
            if not self._is_rulingdigital_detail(detail_url):
                continue

            raw_rows += 1
            title = _normalize_text(anchor.get_text(" ", strip=True))
            if not title:
                continue
            context = _nearest_detail_context(anchor, detail_url)
            records.append(
                Scholarship.from_raw(
                    self.config.source_id,
                    title,
                    _extract_date(context, detail_url),
                    detail_url,
                    entry_url=self.config.entry_url,
                    detail_url=detail_url,
                )
            )

        return records, raw_rows

    def _is_rulingdigital_detail(self, url: str) -> bool:
        if not self._host_allowed(url):
            return False
        path = urlparse(url).path.lower()
        return path.startswith("/p/406-") and path.endswith(".php")


def _nearest_detail_context(anchor: Tag, detail_url: str) -> str:
    """取得同列／近鄰文字；一找到日期即停止向外擴張。"""

    anchor_text = _normalize_text(anchor.get_text(" ", strip=True))
    parent: Tag | None = anchor
    last_context = anchor_text

    for _ in range(4):
        candidate = parent.parent
        if not isinstance(candidate, Tag):
            break
        parent = candidate
        context = _normalize_text(parent.get_text(" ", strip=True))
        if context:
            last_context = context
        if _extract_date(context, detail_url):
            return context
        if parent.name in {"li", "tr", "article"}:
            break

    return last_context
