# -*- coding: utf-8 -*-

from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
    _contains_scholarship_marker,
    _extract_date,
    _normalize_text,
)
from src.models.scholarship import Scholarship


class WordPressArchiveScholarshipCollector(AdditionalScholarshipSourceCollector):
    """解析 WordPress 類文章 archive，避免掃描導覽與側欄連結。"""

    # 只把 archive 文章容器視為原始列，避免 generic 全頁 anchor 噪音。
    def _parse_html(self, html: str, page_url: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        articles = _archive_articles(soup)
        records = [
            record
            for article in articles
            if (record := self._parse_article(article, page_url)) is not None
        ]
        return records, len(articles)

    # 從單一文章卡片取得標題、日期與 detail URL。
    def _parse_article(self, article: Tag, page_url: str) -> Scholarship | None:
        anchor = _article_title_anchor(article)
        if anchor is None:
            return None
        title = _normalize_text(anchor.get_text(" ", strip=True))
        if not title or not _contains_scholarship_marker(title):
            return None
        detail_url = urljoin(page_url, str(anchor.get("href", "")).strip())
        if not detail_url or not self._host_allowed(detail_url):
            return None
        context = _normalize_text(article.get_text(" ", strip=True))
        published_date = _article_date(article, context, detail_url)
        return Scholarship.from_raw(
            self.config.source_id,
            title,
            published_date,
            detail_url,
            entry_url=self.config.entry_url,
            detail_url=detail_url,
        )


# WordPress 主題通常使用 article 或 type-post；去重避免 article.type-post 重複命中。
def _archive_articles(soup: BeautifulSoup) -> list[Tag]:
    articles: list[Tag] = []
    seen: set[int] = set()
    for candidate in soup.select("article, .type-post"):
        if not isinstance(candidate, Tag) or id(candidate) in seen:
            continue
        seen.add(id(candidate))
        articles.append(candidate)
    return articles


# 優先使用 WordPress entry-title，缺少時才退回文章內第一個有文字的 href。
def _article_title_anchor(article: Tag) -> Tag | None:
    candidate = article.select_one(".entry-title a[href]")
    if isinstance(candidate, Tag):
        return candidate
    for anchor in article.find_all("a", href=True):
        if isinstance(anchor, Tag) and _normalize_text(anchor.get_text(" ", strip=True)):
            return anchor
    return None


# 優先採 time datetime；否則沿用既有日期抽取規則。
def _article_date(article: Tag, context: str, detail_url: str) -> str:
    time_tag = article.find("time")
    if isinstance(time_tag, Tag):
        raw_datetime = str(time_tag.get("datetime", "")).strip()
        if len(raw_datetime) >= 10:
            parsed = _extract_date(raw_datetime[:10], detail_url)
            if parsed:
                return parsed
    return _extract_date(context, detail_url)
