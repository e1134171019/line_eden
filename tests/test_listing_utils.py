# -*- coding: utf-8 -*-

from src.collectors.listing_utils import (
    detect_total_pages,
    dyna_page_urls,
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


# DYNA CMS 使用 JavaScript page list 時，應由 urlPrefix 生成實際網址。
def test_dyna_javascript_pagination_is_generated() -> None:
    base_url = "https://www.lhu.edu.tw/p/422-1000-4.php?Lang=zh-tw"
    html = """
    <script>
    var option = {
      urlPrefix: 'https://www.lhu.edu.tw/p/422-1000-4-PAGE.php?Lang=zh-tw',
      totalPage: 5
    };
    </script>
    <a class="_cgptlist_gopage" href="javascript:void(0)">2</a>
    """

    assert detect_total_pages(html) == 5
    assert dyna_page_urls(html, base_url) == [
        (2, "https://www.lhu.edu.tw/p/422-1000-4-2.php?Lang=zh-tw"),
        (3, "https://www.lhu.edu.tw/p/422-1000-4-3.php?Lang=zh-tw"),
        (4, "https://www.lhu.edu.tw/p/422-1000-4-4.php?Lang=zh-tw"),
        (5, "https://www.lhu.edu.tw/p/422-1000-4-5.php?Lang=zh-tw"),
    ]
    assert numbered_page_urls(html, base_url) == []


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
