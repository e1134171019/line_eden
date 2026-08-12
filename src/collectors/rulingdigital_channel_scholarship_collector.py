# -*- coding: utf-8 -*-

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
    _extract_date,
    _normalize_text,
)
from src.models.scholarship import Scholarship


class RulingDigitalChannelScholarshipCollector(AdditionalScholarshipSourceCollector):
    """解析 RulingDigital `/p/412` channel 中的同站 `/p/405` 公告。"""

    # 只把同站 /p/405 公告視為候選，避免導覽與其他 CMS 頁型污染。
    def _parse_html(self, html: str, page_url: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        raw_rows = 0
        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag):
                continue
            detail_url = urljoin(page_url, str(anchor.get("href", "")).strip())
            if not self._is_channel_detail(detail_url):
                continue
            raw_rows += 1
            record = self._build_record(anchor, detail_url)
            if record is not None:
                records.append(record)
        return records, raw_rows

    # `/p/405` 是此 family 的內容頁契約；其他頁型或外站一律排除。
    def _is_channel_detail(self, url: str) -> bool:
        if not self._host_allowed(url):
            return False
        path = urlparse(url).path.lower()
        return path.startswith("/p/405-") and path.endswith(".php")

    # 標題中的申請截止日不得被誤當成公告發布日。
    def _build_record(self, anchor: Tag, detail_url: str) -> Scholarship | None:
        title = _normalize_text(anchor.get_text(" ", strip=True))
        if not title:
            return None
        context = _independent_date_context(anchor)
        return Scholarship.from_raw(
            self.config.source_id,
            title,
            _extract_date(context, ""),
            detail_url,
            entry_url=self.config.entry_url,
            detail_url=detail_url,
        )


# 往同列／近鄰外擴，但排除 anchor 本身文字，避免把 deadline 當 published_date。
def _independent_date_context(anchor: Tag) -> str:
    parent: Tag | None = anchor
    for _ in range(4):
        candidate = parent.parent
        if not isinstance(candidate, Tag):
            break
        parent = candidate
        context = _text_outside_anchor(parent, anchor)
        if _extract_date(context, ""):
            return context
        if parent.name in {"li", "tr", "article"}:
            break
    return ""


# 收集祖先容器文字時忽略 anchor 子樹，保留日期欄與相鄰 metadata。
def _text_outside_anchor(root: Tag, anchor: Tag) -> str:
    parts: list[str] = []
    for node in root.find_all(string=True):
        if any(parent is anchor for parent in node.parents):
            continue
        text = _normalize_text(str(node))
        if text:
            parts.append(text)
    return " ".join(parts)
