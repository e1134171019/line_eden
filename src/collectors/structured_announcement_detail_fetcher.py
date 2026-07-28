# -*- coding: utf-8 -*-

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher


class StructuredAnnouncementDetailFetcher(AnnouncementDetailFetcher):
    """以 DetailFetchResult 結構欄位傳遞附件狀態，不在文字中插入 marker。"""

    def _combine_text(self, body: str, attachment_texts: list[str]) -> str:
        parts = [body, *(text for text in attachment_texts if text.strip())]
        return "\n".join(part for part in parts if part.strip())

    def _apply_rules_status_marker(self, text: str, rules_status: str) -> str:
        # rules_status 已由 DetailFetchResult 獨立保存，不污染正文內容。
        return text
