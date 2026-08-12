# -*- coding: utf-8 -*-

from urllib.parse import parse_qsl, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
    _extract_date,
    _normalize_text,
)
from src.models.scholarship import Scholarship


class TadnewsCategoryScholarshipCollector(AdditionalScholarshipSourceCollector):
    """解析 Tadnews 指定 category 中的正式 nsn 公告。"""

    # 只接受同站、同 category、具數字 nsn 的 Tadnews detail URL。
    def _parse_html(self, html: str, page_url: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        raw_rows = 0
        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag):
                continue
            detail_url = urljoin(page_url, str(anchor.get("href", "")).strip())
            if not self._is_tadnews_detail(detail_url):
                continue
            raw_rows += 1
            title = _normalize_text(anchor.get_text(" ", strip=True))
            if not title:
                continue
            records.append(
                Scholarship.from_raw(
                    self.config.source_id,
                    title,
                    _extract_date(_independent_date_context(anchor), ""),
                    detail_url,
                    entry_url=self.config.entry_url,
                    detail_url=detail_url,
                )
            )
        return records, raw_rows

    def _is_tadnews_detail(self, url: str) -> bool:
        if not self._host_allowed(url):
            return False
        parsed = urlparse(url)
        if not parsed.path.casefold().endswith("/modules/tadnews/index.php"):
            return False
        nsn = _query_value(url, "nsn")
        if not nsn.isdigit():
            return False
        expected_category = _query_value(self.config.entry_url, "ncsn")
        if not expected_category:
            return True
        return _query_value(url, "ncsn") == expected_category


def _query_value(url: str, name: str) -> str:
    target = name.casefold()
    for key, value in parse_qsl(urlparse(url).query, keep_blank_values=True):
        if key.casefold() == target:
            return value.strip()
    return ""


# 只讀取標題之外的近鄰 metadata，避免把申請截止日當成發布日。
def _independent_date_context(anchor: Tag) -> str:
    parent: Tag | None = anchor
    for _ in range(4):
        candidate = parent.parent
        if not isinstance(candidate, Tag):
            break
        parent = candidate
        parts: list[str] = []
        for node in parent.find_all(string=True):
            if any(node_parent is anchor for node_parent in node.parents):
                continue
            text = _normalize_text(str(node))
            if text:
                parts.append(text)
        context = " ".join(parts)
        if _extract_date(context, ""):
            return context
        if parent.name in {"li", "tr", "article"}:
            break
    return ""
