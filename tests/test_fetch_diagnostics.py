# -*- coding: utf-8 -*-

import httpx
import pytest

import src.collectors.announcement_detail_fetcher as fetcher_module
from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.models.scholarship import Scholarship


# 建立使用固定安全限制的測試擷取器。
def _fetcher() -> AnnouncementDetailFetcher:
    return AnnouncementDetailFetcher(10.0, "ScholarshipAgentTest/1.0", 3, 1024 * 1024, 10)


# 建立測試公告。
def _item(url: str) -> Scholarship:
    return Scholarship.from_raw("lhu", "能源獎學金", "2026-07-27", url)


# 將 httpx.Client 換成 MockTransport 支援的 Client。
def _patch_client(monkeypatch: pytest.MonkeyPatch, handler: object) -> None:
    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    # 保留正式 Client 設定，只替換底層網路傳輸。
    def client_factory(**kwargs: object) -> httpx.Client:
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(fetcher_module.httpx, "Client", client_factory)


# 驗證附件成功解析時保留請求網址、最終網址與文字長度。
def test_attachment_success_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <article><h1>能源獎學金</h1><p>資格請見附件。</p>
    <a href="/files/rules.pdf">評選辦法.pdf</a></article>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/files/rules.pdf":
            return httpx.Response(302, headers={"Location": "/download/final.pdf"})
        if request.url.path == "/download/final.pdf":
            return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"pdf")
        return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"}, text=html)

    _patch_client(monkeypatch, handler)
    monkeypatch.setattr(fetcher_module, "extract_document_text", lambda *_: "電子系可申請。")

    result = _fetcher().fetch_with_diagnostics(_item("https://activity.lhu.edu.tw/news/1"))

    attachment = result.attachments[0]
    assert result.discovered_attachment_count == 1
    assert result.successful_attachment_count() == 1
    assert attachment.requested_url.endswith("/files/rules.pdf")
    assert attachment.final_url.endswith("/download/final.pdf")
    assert attachment.content_type == "application/pdf"
    assert attachment.text_length == len("電子系可申請。")


# 驗證附件下載失敗時保留 HTTP 錯誤，而正文仍可供判斷。
def test_attachment_failure_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <article><h1>能源獎學金</h1><p>一般大專生可申請。</p>
    <a href="/files/rules.pdf">資格辦法.pdf</a></article>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("rules.pdf"):
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text=html)

    _patch_client(monkeypatch, handler)

    result = _fetcher().fetch_with_diagnostics(_item("https://activity.lhu.edu.tw/news/2"))

    attachment = result.attachments[0]
    assert "一般大專生可申請" in result.text
    assert attachment.status == "error"
    assert "HTTPStatusError" in attachment.error
    assert "503" in attachment.error


# 驗證短網址來源失敗時不拋出例外，改由 audit 顯示錯誤原因。
def test_source_failure_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "reurl.cc":
            return httpx.Response(302, headers={"Location": "https://files.example.com/missing.pdf"})
        return httpx.Response(404, text="missing")

    _patch_client(monkeypatch, handler)

    result = _fetcher().fetch_with_diagnostics(_item("https://reurl.cc/example"))

    assert result.text == ""
    assert result.source.status == "error"
    assert result.source.requested_url == "https://reurl.cc/example"
    assert "HTTPStatusError" in result.source.error
    assert "404" in result.source.error
