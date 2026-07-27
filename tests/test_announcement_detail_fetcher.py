# -*- coding: utf-8 -*-

import pytest

from config import ATTACHMENT_TEXT_MARKER
from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher


# 建立具有固定安全限制的測試擷取器。
def _fetcher() -> AnnouncementDetailFetcher:
    return AnnouncementDetailFetcher(
        timeout_seconds=10.0,
        user_agent="ScholarshipAgentTest/1.0",
        max_attachment_count=3,
        max_download_bytes=1024 * 1024,
        max_pdf_pages=10,
    )


# 驗證公告內頁會移除腳本與樣式並保留可判斷文字。
def test_parse_detail_html_to_plain_text() -> None:
    html = """
    <html>
      <head><style>.hidden { display: none; }</style></head>
      <body>
        <script>ignore_me()</script>
        <main>申請對象為大專院校電子工程系在校生，學業平均八十分以上。</main>
      </body>
    </html>
    """

    text = _fetcher()._parse_text(html)

    assert "電子工程系" in text
    assert "ignore_me" not in text
    assert "display" not in text


# 驗證頁首、導覽列與頁尾的電子郵件不會污染公告正文。
def test_parse_detail_excludes_navigation_and_footer_noise() -> None:
    html = """
    <body>
      <header>龍華科技大學電子工程系</header>
      <nav>首頁 電機工程系 進修部</nav>
      <article><h1>就學貸款修正辦法</h1><p>本次公告說明條文修正內容。</p></article>
      <footer>聯絡電子郵件：service@example.com</footer>
    </body>
    """

    text = _fetcher()._parse_text(html, "就學貸款修正辦法")

    assert "條文修正內容" in text
    assert "電子郵件" not in text
    assert "電子工程系" not in text
    assert "進修部" not in text


# 驗證龍華活動網站優先選擇 mpgdetail，不包含共用活動橫幅。
def test_activity_site_uses_detail_container() -> None:
    html = """
    <body>
      <div class="banner">2024全國創意宋江陣頭大賽</div>
      <div class="page-wrapper">
        <div class="mpgdetail">
          <h2>能源工程獎學金</h2>
          <p>申請資格限電子工程相關科系學生。</p>
        </div>
      </div>
    </body>
    """

    text = _fetcher()._parse_text(
        html,
        "能源工程獎學金",
        "https://activity.lhu.edu.tw/p/404-1051-1.php",
    )

    assert "電子工程相關科系" in text
    assert "宋江陣頭" not in text


# 驗證成功解析附件時會加入附件內容標記。
def test_combine_text_marks_resolved_attachments() -> None:
    text = _fetcher()._combine_text("公告正文", ["附件資格內容"])

    assert ATTACHMENT_TEXT_MARKER in text
    assert "附件資格內容" in text


# 驗證找不到足夠正文時採失敗關閉。
def test_parse_detail_rejects_unreliable_content() -> None:
    with pytest.raises(ValueError, match="無法可靠定位"):
        _fetcher()._parse_text("<html><body><nav>首頁</nav></body></html>")
