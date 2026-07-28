# -*- coding: utf-8 -*-

import pytest

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.diagnostics.detail_fetch_diagnostics import (
    ExtractedAttachment,
    RULES_STATUS_DECLARED_MISSING,
    RULES_STATUS_DISCOVERED_UNRESOLVED,
)
from src.extractors.attachment_link_extractor import AttachmentLinkInventory


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


# 正文與已確認主要辦法只以換行組合，不加入控制語意 marker。
def test_combine_text_joins_resolved_rules_without_marker() -> None:
    text = _fetcher()._combine_text("公告正文", ["附件資格內容"])

    assert text == "公告正文\n附件資格內容"


# 公告明示資格在附件但完全找不到附件連結時，結構化狀態必須失敗關閉。
def test_declared_attachment_without_link_has_missing_status() -> None:
    body = "相關助學金項目及內容，請參考附件。學業平均80分以上。"
    inventory = AttachmentLinkInventory(tuple(), 0)

    status = _fetcher()._determine_rules_status(body, inventory, tuple())

    assert status == RULES_STATUS_DECLARED_MISSING


# 次要證明文件成功不能掩蓋主要辦法解析失敗。
def test_supporting_document_does_not_resolve_failed_rules() -> None:
    inventory = AttachmentLinkInventory(
        selected_urls=(
            "https://example.com/rules.pdf",
            "https://example.com/proof.docx",
        ),
        discovered_count=2,
        selected_roles=("rules", "supporting_document"),
        discovered_rules_count=1,
        selected_labels=("申請辦法", "證明書"),
    )
    attachments = (
        ExtractedAttachment(
            "https://example.com/rules.pdf",
            "https://example.com/rules.pdf",
            "申請辦法",
            "rules",
            "uncertain",
            "pdf",
            "error",
            "",
            "掃描檔",
        ),
        ExtractedAttachment(
            "https://example.com/proof.docx",
            "https://example.com/proof.docx",
            "證明書",
            "supporting_document",
            "supporting_document",
            "docx",
            "success",
            "申請人證明資料",
        ),
    )

    status = _fetcher()._determine_rules_status("公告正文", inventory, attachments)

    assert status == RULES_STATUS_DISCOVERED_UNRESOLVED


# 驗證找不到足夠正文時採失敗關閉。
def test_parse_detail_rejects_unreliable_content() -> None:
    with pytest.raises(ValueError, match="無法可靠定位"):
        _fetcher()._parse_text("<html><body><nav>首頁</nav></body></html>")
