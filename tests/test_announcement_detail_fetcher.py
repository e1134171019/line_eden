# -*- coding: utf-8 -*-

import pytest

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher


# 驗證公告內頁會移除腳本與樣式並保留可判斷文字。
def test_parse_detail_html_to_plain_text() -> None:
    fetcher = AnnouncementDetailFetcher(10.0, "ScholarshipAgentTest/1.0")
    html = """
    <html>
      <head><style>.hidden { display: none; }</style></head>
      <body>
        <script>ignore_me()</script>
        <main>申請對象為大專院校電子工程系在校生，學業平均八十分以上。</main>
      </body>
    </html>
    """

    text = fetcher._parse_text(html)

    assert "電子工程系" in text
    assert "ignore_me" not in text
    assert "display" not in text


# 驗證頁首、導覽列與頁尾的電子郵件不會污染公告正文。
def test_parse_detail_excludes_navigation_and_footer_noise() -> None:
    fetcher = AnnouncementDetailFetcher(10.0, "ScholarshipAgentTest/1.0")
    html = """
    <body>
      <header>龍華科技大學電子工程系</header>
      <nav>首頁 電機工程系 進修部</nav>
      <article><h1>就學貸款修正辦法</h1><p>本次公告說明條文修正內容。</p></article>
      <footer>聯絡電子郵件：service@example.com</footer>
    </body>
    """

    text = fetcher._parse_text(html, "就學貸款修正辦法")

    assert "條文修正內容" in text
    assert "電子郵件" not in text
    assert "電子工程系" not in text
    assert "進修部" not in text


# 驗證找不到足夠正文時採失敗關閉。
def test_parse_detail_rejects_unreliable_content() -> None:
    fetcher = AnnouncementDetailFetcher(10.0, "ScholarshipAgentTest/1.0")

    with pytest.raises(ValueError, match="無法可靠定位"):
        fetcher._parse_text("<html><body><nav>首頁</nav></body></html>")
