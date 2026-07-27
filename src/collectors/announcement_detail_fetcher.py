# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup
import httpx

from src.models.scholarship import Scholarship


class AnnouncementDetailFetcher:
    """下載公告內頁並轉為資格判斷可用的純文字。"""

    # 初始化 HTTP timeout 與 User-Agent。
    def __init__(self, timeout_seconds: float, user_agent: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    # 下載指定公告內頁並移除腳本與樣式內容。
    def fetch_text(self, scholarship: Scholarship) -> str:
        response = httpx.get(
            scholarship.source_url,
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        return self._parse_text(response.text)

    # 將公告 HTML 轉成壓縮空白後的純文字。
    def _parse_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for node in soup.select("script, style, noscript"):
            node.decompose()
        return " ".join(soup.get_text(" ", strip=True).split())
