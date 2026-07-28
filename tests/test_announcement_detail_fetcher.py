# -*- coding: utf-8 -*-

import pytest

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.diagnostics.detail_fetch_diagnostics import (
    ExtractedAttachment,
    RULES_STATUS_DECLARED_MISSING,
    RULES_STATUS_DISCOVERED_UNRESOLVED,
)
from src.extractors.attachment_link_extractor import AttachmentLinkInventory


def _fetcher() -> AnnouncementDetailFetcher:
    return AnnouncementDetailFetcher(10.0, "ScholarshipAgentTest/1.0", 3, 1024 * 1024, 10)


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


def test_parse_detail_excludes_navigation_and_footer_noise() -> None:
    html = """
    <header>龍華科技大學電子工程系</header><nav>首頁 進修部</nav>
    <article><h1>就學貸款修正辦法</h1><p>本次公告說明條文修正內容。</p></article>
    <footer>service@example.com</footer>
    """
    text = _fetcher()._parse_text(html, "就學貸款修正辦法")
    assert "條文修正內容" in text
    assert "電子工程系" not in text
    assert "進修部" not in text


def test_activity_site_uses_detail_container() -> None:
    html = """
    <div class="banner">宋江陣頭大賽</div>
    <div class="mpgdetail"><h2>能源工程獎學金</h2><p>申請資格限電子工程相關科系學生。</p></div>
    """
    text = _fetcher()._parse_text(
        html,
        "能源工程獎學金",
        "https://activity.lhu.edu.tw/p/404-1051-1.php",
    )
    assert "電子工程相關科系" in text
    assert "宋江陣頭" not in text


def test_combine_text_has_no_control_marker() -> None:
    assert _fetcher()._combine_text("公告正文", ["附件資格內容"]) == "公告正文\n附件資格內容"


def test_declared_attachment_without_link_has_missing_status() -> None:
    inventory = AttachmentLinkInventory(tuple(), 0)
    status = _fetcher()._determine_rules_status(
        "相關助學金項目及內容，請參考附件。",
        inventory,
        tuple(),
    )
    assert status == RULES_STATUS_DECLARED_MISSING


def test_supporting_document_does_not_resolve_failed_rules() -> None:
    inventory = AttachmentLinkInventory(
        selected_urls=("https://example.com/rules.pdf", "https://example.com/proof.docx"),
        discovered_count=2,
        selected_roles=("rules", "supporting_document"),
        discovered_rules_count=1,
        selected_labels=("申請辦法", "證明書"),
    )
    attachments = (
        ExtractedAttachment(
            "https://example.com/rules.pdf", "", "申請辦法", "rules",
            "uncertain", "pdf", "error", "", "掃描檔",
        ),
        ExtractedAttachment(
            "https://example.com/proof.docx", "", "證明書", "supporting_document",
            "supporting_document", "docx", "success", "申請人證明資料",
        ),
    )
    assert _fetcher()._determine_rules_status("公告正文", inventory, attachments) == RULES_STATUS_DISCOVERED_UNRESOLVED


def test_parse_detail_rejects_unreliable_content() -> None:
    with pytest.raises(ValueError, match="無法可靠定位"):
        _fetcher()._parse_text("<html><body><nav>首頁</nav></body></html>")
