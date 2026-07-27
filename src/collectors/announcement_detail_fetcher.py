# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

import httpx

from config import ATTACHMENT_TEXT_MARKER
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
    """下載公告正文與支援格式附件，合併為資格判斷文字。"""

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

    # 下載公告；短網址、直接文件與 HTML 附件均依最終回應處理。
    def fetch_text(self, scholarship: Scholarship) -> str:
        headers = {"User-Agent": self.user_agent}
        with httpx.Client(headers=headers, timeout=self.timeout_seconds, follow_redirects=True) as client:
            resource = self._download(client, scholarship.source_url)
            kind = detect_document_kind(resource.content_type, resource.url)
            if kind != "unsupported":
                return self._document_text(resource)
            return self._html_with_attachments(client, resource, scholarship.title)

    # 下載 HTML 正文並合併可成功解析的附件內容。
    def _html_with_attachments(
        self,
        client: httpx.Client,
        resource: DownloadedResource,
        title: str,
    ) -> str:
        html = self._decode_html(resource)
        body = extract_announcement_text(html, title, resource.url)
        links = extract_attachment_links(html, resource.url, title, self.max_attachment_count)
        attachment_texts = [text for url in links if (text := self._attachment_text(client, url))]
        return self._combine_text(body, attachment_texts)

    # 下載單一附件；不支援、過大或無文字時保守忽略。
    def _attachment_text(self, client: httpx.Client, url: str) -> str:
        try:
            resource = self._download(client, url)
            kind = detect_document_kind(resource.content_type, resource.url)
            if kind != "unsupported":
                return self._document_text(resource)
            if self._is_html(resource):
                return extract_announcement_text(self._decode_html(resource), "", resource.url)
        except (httpx.HTTPError, ValueError):
            return ""
        return ""

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
