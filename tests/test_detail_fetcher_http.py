# -*- coding: utf-8 -*-

import httpx
import pytest

import src.collectors.announcement_detail_fetcher as fetcher_module
from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_RESOLVED
from src.extractors.attachment_content_classifier import CONTENT_RULES
from src.models.scholarship import Scholarship


# 建立測試擷取器。
def _fetcher(max_download_bytes: int = 1024 * 1024) -> AnnouncementDetailFetcher:
    return AnnouncementDetailFetcher(
        timeout_seconds=10.0,
        user_agent="ScholarshipAgentTest/1.0",
        max_attachment_count=3,
        max_download_bytes=max_download_bytes,
        max_pdf_pages=10,
    )


# 建立測試公告。
def _item(url: str) -> Scholarship:
    return Scholarship.from_raw("lhu", "能源獎學金", "2026-07-27", url)


# 將 httpx.Client 換成 MockTransport 支援的真實 Client。
def _patch_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: object,
) -> None:
    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs: object) -> httpx.Client:
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(fetcher_module.httpx, "Client", client_factory)


# 驗證 HTML 公告會以結構化欄位保存正文與主要辦法文字。
def test_fetch_html_and_attachment_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <div class="mpgdetail">
      <h2>能源獎學金</h2>
      <p>申請資格請參閱附件。</p>
      <a href="/files/rules.pdf">評選辦法.pdf</a>
    </div>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("rules.pdf"):
            return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"pdf")
        return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"}, text=html)

    _patch_client(monkeypatch, handler)
    monkeypatch.setattr(
        fetcher_module,
        "extract_document_text",
        lambda *_: "申請資格限電子工程相關科系學生，學業成績80分以上。",
    )

    result = _fetcher().fetch_with_diagnostics(
        _item("https://activity.lhu.edu.tw/news/1")
    )

    assert result.rules_status == RULES_STATUS_RESOLVED
    assert "申請資格請參閱附件" in result.body_text
    assert "電子工程相關科系" in result.text
    assert len(result.extracted_attachments) == 1
    assert result.extracted_attachments[0].content_role == CONTENT_RULES
    assert result.source.extraction_policy_name == "lhu-html"
    assert result.source.selector_used == ".mpgdetail"
    assert result.source.extraction_fallback is False
    assert len(result.extraction_policy_hash) == 64


# 驗證短網址重新導向至 PDF 時會依最終內容類型解析。
def test_short_url_redirects_to_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "reurl.cc":
            return httpx.Response(302, headers={"Location": "https://files.example.com/rules.pdf"})
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"pdf")

    _patch_client(monkeypatch, handler)
    monkeypatch.setattr(fetcher_module, "extract_document_text", lambda *_: "大專學生可申請。")

    result = _fetcher().fetch_with_diagnostics(_item("https://reurl.cc/example"))

    assert result.text == "大專學生可申請。"
    assert result.source.extraction_policy_name == "document-pdf"
    assert len(result.extraction_policy_hash) == 64


# 驗證宣告檔案過大時在讀取前拒絕下載。
def test_rejects_large_content_length(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html", "Content-Length": "1000"},
            content=b"small",
        )

    _patch_client(monkeypatch, handler)

    with pytest.raises(ValueError, match="超過安全上限"):
        _fetcher(max_download_bytes=100).fetch_text(_item("https://example.com/news"))
