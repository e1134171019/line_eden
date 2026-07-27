# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

import httpx

from config import ATTACHMENT_TEXT_MARKER, UNRESOLVED_ATTACHMENT_MARKER
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.extractors.announcement_content_extractor import extract_announcement_text
from src.extractors.attachment_link_extractor import RULES, extract_attachment_inventory
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
            requested_url = scholarship.source_url
            resource = self._download(client, requested_url)
            kind = detect_document_kind(resource.content_type, resource.url)
            if kind != "unsupported":
                return self._direct_document_result(resource, kind, requested_url)
            if not self._is_html(resource):
                raise ValueError("來源不是支援文件或 HTML")
            return self._html_result(client, resource, scholarship.title, requested_url)

    # 建立直接 PDF 或 DOCX 來源的成功結果。
    def _direct_document_result(
        self,
        resource: DownloadedResource,
        kind: str,
        requested_url: str,
    ) -> DetailFetchResult:
        text = self._document_text(resource)
        source = self._success_diagnostic("source", requested_url, resource, kind, text)
        return DetailFetchResult(text, source, tuple(), 0)

    # 下載 HTML 正文並收集每個附件的解析診斷。
    def _html_result(
        self,
        client: httpx.Client,
        resource: DownloadedResource,
        title: str,
        requested_url: str,
    ) -> DetailFetchResult:
        html = self._decode_html(resource)
        body = extract_announcement_text(html, title, resource.url)
        inventory = extract_attachment_inventory(
            html,
            resource.url,
            title,
            self.max_attachment_count,
        )
        results = [
            self._attachment_result(client, url, inventory.role_at(index))
            for index, url in enumerate(inventory.selected_urls)
        ]
        rules_texts = [
            text
            for text, diagnostic in results
            if diagnostic.status == "success" and diagnostic.attachment_role == RULES
        ]
        diagnostics = tuple(diagnostic for _, diagnostic in results)
        source = self._success_diagnostic("source", requested_url, resource, "html", body)
        combined = self._combine_text(body, rules_texts)
        combined = self._mark_unresolved_attachments(
            combined,
            inventory.discovered_count,
            rules_texts,
            body,
            diagnostics,
            inventory.discovered_rules_count,
        )
        return DetailFetchResult(combined, source, diagnostics, inventory.discovered_count)

    # 主要辦法未取得，或公告明示資格在附件時加入安全標記。
    def _mark_unresolved_attachments(
        self,
        text: str,
        discovered_count: int,
        attachment_texts: list[str],
        body_text: str = "",
        diagnostics: tuple[ResourceDiagnostic, ...] = tuple(),
        discovered_rules_count: int = 0,
    ) -> str:
        resolved_rules = any(
            item.status == "success" and item.attachment_role == RULES
            for item in diagnostics
        )
        rules_missing = discovered_rules_count > 0 and not resolved_rules
        declared_missing = _body_requires_rules(body_text or text) and not resolved_rules
        all_failed = discovered_count > 0 and not attachment_texts
        if rules_missing or declared_missing or all_failed:
            return f"{text}\n{UNRESOLVED_ATTACHMENT_MARKER}"
        return text

    # 下載並解析單一附件，完整保留成功、忽略或錯誤原因。
    def _attachment_result(
        self,
        client: httpx.Client,
        requested_url: str,
        attachment_role: str = "unknown",
    ) -> tuple[str, ResourceDiagnostic]:
        resource: DownloadedResource | None = None
        kind = "unknown"
        try:
            resource = self._download(client, requested_url)
            kind = detect_document_kind(resource.content_type, resource.url)
            text = self._resource_text(resource, kind)
            diagnostic = self._success_diagnostic(
                "attachment",
                requested_url,
                resource,
                kind,
                text,
                attachment_role,
            )
            return text, diagnostic
        except Exception as error:
            return "", self._error_diagnostic(
                requested_url,
                resource,
                kind,
                error,
                attachment_role,
            )

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
        attachment_role: str = "unknown",
    ) -> ResourceDiagnostic:
        return ResourceDiagnostic(
            role,
            requested_url,
            resource.url,
            resource.content_type,
            len(resource.content),
            kind,
            "success",
            len(text),
            "",
            attachment_role,
        )

    # 建立附件下載或解析失敗診斷。
    def _error_diagnostic(
        self,
        requested_url: str,
        resource: DownloadedResource | None,
        kind: str,
        error: Exception,
        attachment_role: str = "unknown",
    ) -> ResourceDiagnostic:
        final_url = resource.url if resource else ""
        content_type = resource.content_type if resource else ""
        size_bytes = len(resource.content) if resource else 0
        return ResourceDiagnostic(
            "attachment",
            requested_url,
            final_url,
            content_type,
            size_bytes,
            kind,
            "error",
            0,
            self._error_text(error),
            attachment_role,
        )

    # 建立公告來源下載或解析失敗結果。
    def _source_failure(self, requested_url: str, error: Exception) -> DetailFetchResult:
        source = ResourceDiagnostic(
            "source",
            requested_url,
            "",
            "",
            0,
            "unknown",
            "error",
            0,
            self._error_text(error),
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

    # 正文後只在主要資格辦法成功解析時加入附件內容標記。
    def _combine_text(self, body: str, attachment_texts: list[str]) -> str:
        if not attachment_texts:
            return body
        attachments = "\n".join(attachment_texts)
        return f"{body}\n{ATTACHMENT_TEXT_MARKER}\n{attachments}"

    # 保留既有測試可直接驗證 HTML 解析。
    def _parse_text(self, html: str, title: str = "", source_url: str = "") -> str:
        return extract_announcement_text(html, title, source_url)


# 判斷正文是否明示主要資格、辦法或相關資訊位於附件。
def _body_requires_rules(text: str) -> bool:
    direct = (
        r"(?:相關資訊|申請辦法|相關助學金項目及內容).{0,16}"
        r"(?:請自行下載|自行下載|請參考附件|請參閱附件|詳見附件)"
    )
    subject = r"(?:申請資格|詳細資格|資格條件|申請條件|申請對象)"
    reference = r"(?:詳見|請參閱|請參考|如|依).{0,8}(?:附件|附檔)"
    return bool(re.search(direct, text) or re.search(rf"{subject}.{{0,30}}{reference}", text))
