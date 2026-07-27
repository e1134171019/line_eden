# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

import httpx

from config import ATTACHMENT_TEXT_MARKER
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.extractors.announcement_content_extractor import extract_announcement_text
from src.extractors.attachment_link_extractor import extract_attachment_links
from src.extractors.document_text_extractor import detect_document_kind, extract_document_text
from src.models.scholarship import Scholarship


@dataclass(frozen=True)
class DownloadedResource:
    """單次 HTTP 下載後的最終網址、內容類型與位元資料。"""

    url: str
    content_type: str
    content: bytes


class AnnouncementDetailFetcher:
    """下載公告正文與附件，並提供稽核所需診斷。"""

    # 初始化 HTTP 與附件解析安全限制。
    def __init__(
        self,
        timeout_seconds: float,
        user_agent: str,
        max_attachment_count: int,
        max_download_bytes: int,
        max_pdf_pages: int,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.max_attachment_count = max_attachment_count
        self.max_download_bytes = max_download_bytes
        self.max_pdf_pages = max_pdf_pages

    # 正式流程擷取文字，來源下載或正文解析失敗時保留例外。
    def fetch_text(self, scholarship: Scholarship) -> str:
        return self._fetch_result(scholarship).text

    # 稽核流程擷取文字並將來源失敗轉成可顯示診斷。
    def fetch_with_diagnostics(self, scholarship: Scholarship) -> DetailFetchResult:
        try:
            return self._fetch_result(scholarship)
        except Exception as error:
            return self._source_failure(scholarship.source_url, error)

    # 依來源最終格式處理直接文件或 HTML 公告。
    def _fetch_result(self, scholarship: Scholarship) -> DetailFetchResult:
        headers = {"User-Agent": self.user_agent}
        with httpx.Client(headers=headers, timeout=self.timeout_seconds, follow_redirects=True) as client:
            resource = self._download(client, scholarship.source_url)
            kind = detect_document_kind(resource.content_type, resource.url)
            if kind != "unsupported":
                return self._direct_document_result(resource, kind)
            if not self._is_html(resource):
                raise ValueError("來源不是支援文件或 HTML")
            return self._html_result(client, resource, scholarship.title)

    # 建立直接 PDF 或 DOCX 來源的成功結果。
    def _direct_document_result(self, resource: DownloadedResource, kind: str) -> DetailFetchResult:
        text = self._document_text(resource)
        source = self._success_diagnostic("source", resource.url, resource, kind, text)
        return DetailFetchResult(text, source, tuple(), 0)

    # 下載 HTML 正文並收集每個附件的解析診斷。
    def _html_result(
        self,
        client: httpx.Client,
        resource: DownloadedResource,
        title: str,
    ) -> DetailFetchResult:
        html = self._decode_html(resource)
        body = extract_announcement_text(html, title, resource.url)
        links = extract_attachment_links(html, resource.url, title, self.max_attachment_count)
        results = [self._attachment_result(client, url) for url in links]
        texts = [text for text, diagnostic in results if diagnostic.status == "success"]
        diagnostics = tuple(diagnostic for _, diagnostic in results)
        source = self._success_diagnostic("source", resource.url, resource, "html", body)
        return DetailFetchResult(self._combine_text(body, texts), source, diagnostics, len(links))

    # 下載並解析單一附件，完整保留成功、忽略或錯誤原因。
    def _attachment_result(
        self,
        client: httpx.Client,
        requested_url: str,
    ) -> tuple[str, ResourceDiagnostic]:
        resource: DownloadedResource | None = None
        kind = "unknown"
        try:
            resource = self._download(client, requested_url)
            kind = detect_document_kind(resource.content_type, resource.url)
            text = self._resource_text(resource, kind)
            diagnostic = self._success_diagnostic("attachment", requested_url, resource, kind, text)
            return text, diagnostic
        except Exception as error:
            return "", self._error_diagnostic(requested_url, resource, kind, error)

    # 依文件、HTML 或不支援格式擷取附件文字。
    def _resource_text(self, resource: DownloadedResource, kind: str) -> str:
        if kind != "unsupported":
            return self._document_text(resource)
        if self._is_html(resource):
            html = self._decode_html(resource)
            return extract_announcement_text(html, "", resource.url)
        raise ValueError("不支援的附件格式")

    # 建立成功下載與解析的資源診斷。
    def _success_diagnostic(
        self,
        role: str,
        requested_url: str,
        resource: DownloadedResource,
        kind: str,
        text: str,
    ) -> ResourceDiagnostic:
        return ResourceDiagnostic(
            role, requested_url, resource.url, resource.content_type,
            len(resource.content), kind, "success", len(text), "",
        )

    # 建立附件下載或解析失敗診斷。
    def _error_diagnostic(
        self,
        requested_url: str,
        resource: DownloadedResource | None,
        kind: str,
        error: Exception,
    ) -> ResourceDiagnostic:
        final_url = resource.url if resource else ""
        content_type = resource.content_type if resource else ""
        size_bytes = len(resource.content) if resource else 0
        return ResourceDiagnostic(
            "attachment", requested_url, final_url, content_type,
            size_bytes, kind, "error", 0, self._error_text(error),
        )

    # 建立公告來源下載或解析失敗結果。
    def _source_failure(self, requested_url: str, error: Exception) -> DetailFetchResult:
        source = ResourceDiagnostic(
            "source", requested_url, "", "", 0, "unknown",
            "error", 0, self._error_text(error),
        )
        return DetailFetchResult("", source, tuple(), 0)

    # 將例外類型與內容限制在單行 240 字內。
    def _error_text(self, error: Exception) -> str:
        message = " ".join(str(error).split())
        return f"{type(error).__name__}: {message}"[:240]

    # 將文件資源交由 PDF 或 DOCX 擷取器處理。
    def _document_text(self, resource: DownloadedResource) -> str:
        return extract_document_text(
            resource.content,
            resource.content_type,
            resource.url,
            self.max_pdf_pages,
        )

    # 使用串流下載並在超過安全上限時中止。
    def _download(self, client: httpx.Client, url: str) -> DownloadedResource:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            self._validate_content_length(response)
            content = self._read_limited(response)
            content_type = response.headers.get("Content-Type", "")
            return DownloadedResource(str(response.url), content_type, content)

    # 依 Content-Length 預先阻擋過大資源。
    def _validate_content_length(self, response: httpx.Response) -> None:
        raw_length = response.headers.get("Content-Length", "0")
        if raw_length.isdigit() and int(raw_length) > self.max_download_bytes:
            raise ValueError("下載檔案超過安全上限")

    # 逐區塊讀取回應，避免未提供 Content-Length 的大型檔案。
    def _read_limited(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > self.max_download_bytes:
                raise ValueError("下載檔案超過安全上限")
            chunks.append(chunk)
        return b"".join(chunks)

    # 依 Content-Type 或內容前綴辨識 HTML。
    def _is_html(self, resource: DownloadedResource) -> bool:
        content_type = resource.content_type.lower()
        prefix = resource.content.lstrip()[:20].lower()
        return "text/html" in content_type or prefix.startswith((b"<!doctype", b"<html"))

    # 依回應宣告 charset 解碼 HTML，無宣告時使用 UTF-8。
    def _decode_html(self, resource: DownloadedResource) -> str:
        match = re.search(r"charset=([^;\s]+)", resource.content_type, re.IGNORECASE)
        encoding = match.group(1).strip('"\'') if match else "utf-8"
        return resource.content.decode(encoding, errors="replace")

    # 正文後只在至少一個附件成功解析時加入附件標記。
    def _combine_text(self, body: str, attachment_texts: list[str]) -> str:
        if not attachment_texts:
            return body
        attachments = "\n".join(attachment_texts)
        return f"{body}\n{ATTACHMENT_TEXT_MARKER}\n{attachments}"

    # 保留既有測試可直接驗證 HTML 解析。
    def _parse_text(self, html: str, title: str = "", source_url: str = "") -> str:
        return extract_announcement_text(html, title, source_url)
