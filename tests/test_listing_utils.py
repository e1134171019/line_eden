# -*- coding: utf-8 -*-

from src.collectors.listing_utils import (
    detect_total_pages,
    next_page_url,
    numbered_page_urls,
)


# 龍華查詢參數分頁應偵測總頁數並保留同一列表網址。
def test_query_string_pagination_is_detected() -> None:
    base_url = "https://www.lhu.edu.tw/p/422-1000-4.php?Lang=zh-tw"
    html = f"""
    <nav>
      <a href="{base_url}">1</a>
      <a href="{base_url}&page=2">2</a>
      <a href="{base_url}&page=3" rel="next">&gt;</a>
    </nav>
    <p>共3頁</p>
    """

    assert detect_total_pages(html) == 3
    assert numbered_page_urls(html, base_url) == [
        (1, base_url),
        (2, f"{base_url}&page=2"),
    ]
    assert next_page_url(html, base_url) == f"{base_url}&page=3"


# `/page/1` 與 `/page/2` 必須視為同一公告列表。
def test_path_pagination_uses_common_listing_root() -> None:
    base_url = (
        "https://www.scholarship.moe.gov.tw/"
        "scholarship/index/index/page/1"
    )
    page_2 = (
        "https://www.scholarship.moe.gov.tw/"
        "scholarship/index/index/page/2"
    )
    html = f"""
    <nav>
      <a href="{base_url}">1</a>
      <a href="{page_2}">2</a>
      <a href="{page_2}" rel="next">下一頁</a>
    </nav>
    """

    assert numbered_page_urls(html, base_url) == [(1, base_url), (2, page_2)]
    assert next_page_url(html, base_url) == page_2


# 不同網域或不同列表根路徑不得被當成分頁。
def test_pagination_rejects_external_and_unrelated_links() -> None:
    base_url = "https://example.test/news/page/1"
    html = """
    <nav>
      <a href="https://outside.test/news/page/2">2</a>
      <a href="https://example.test/other/page/3">3</a>
    </nav>
    """

    assert numbered_page_urls(html, base_url) == []
