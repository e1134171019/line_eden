# -*- coding: utf-8 -*-

from urllib.parse import parse_qsl, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
    _extract_date,
    _normalize_text,
)
from src.models.scholarship import Scholarship


class NpuLatestEventScholarshipCollector(AdditionalScholarshipSourceCollector):
    """解析 NPU LatestEvent 獎助學金列表中的正式 Details.aspx 公告。"""

    # 只把同站 LatestEvent Details.aspx 且具 Parser 的連結視為候選。
    def _parse_html(self, html: str, page_url: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        raw_rows = 0
        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag):
                continue
            detail_url = urljoin(page_url, str(anchor.get("href", "")).strip())
            if not self._is_latestevent_detail(detail_url):
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

    def _is_latestevent_detail(self, url: str) -> bool:
        if not self._host_allowed(url):
            return False
        parsed = urlparse(url)
        if not parsed.path.casefold().endswith("/sub/latestevent/details.aspx"):
            return False
        return any(
            key.casefold() == "parser" and value.strip()
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        )


# 只從標題 anchor 外部的同列 metadata 取公告日期，避免截止日誤判。
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
