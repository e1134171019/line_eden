# -*- coding: utf-8 -*-

import httpx

from src.extractors.announcement_content_extractor import extract_announcement_text
from src.models.scholarship import Scholarship


class AnnouncementDetailFetcher:
    """下載公告內頁並轉為資格判斷可用的正文文字。"""

    # 初始化 HTTP timeout 與 User-Agent。
    def __init__(self, timeout_seconds: float, user_agent: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    # 下載指定公告內頁並只保留公告正文。
    def fetch_text(self, scholarship: Scholarship) -> str:
        response = httpx.get(
            scholarship.source_url,
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        return self._parse_text(response.text, scholarship.title)

    # 將公告 HTML 轉成排除導覽與頁尾的純文字。
    def _parse_text(self, html: str, title: str = "") -> str:
        return extract_announcement_text(html, title)
