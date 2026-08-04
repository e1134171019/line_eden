# -*- coding: utf-8 -*-

from dataclasses import dataclass, replace
from hashlib import sha256
import re

import httpx

from src.collectors.http_client import DetailSafeHttpClient
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    ResourceDiagnostic,
    RULES_STATUS_DECLARED_MISSING,
    RULES_STATUS_DISCOVERED_UNRESOLVED,
    RULES_STATUS_GENERIC_UNCONFIRMED,
    RULES_STATUS_NOT_REQUIRED,
    RULES_STATUS_RESOLVED,
    RULES_STATUS_UNKNOWN,
)
from src.evaluators.attachment_requirement import detect_attachment_requirement
from src.extractors.announcement_content_extractor import extract_announcement_text
from src.extractors.announcement_relevance import content_matches_announcement
from src.extractors.attachment_content_classifier import (
    CONTENT_RULES,
    classify_attachment_content,
)
from src.extractors.attachment_link_extractor import (
    AttachmentLinkInventory,
    extract_attachment_inventory,
)
from src.extractors.document_text_extractor import (
    detect_document_kind,
    extract_document,
    extract_document_text,
)
from src.models.document_evidence import (
    DocumentPageEvidence,
    EXTRACTION_HTML_TEXT,
)
from src.models.scholarship import Scholarship


@dataclass(frozen=True)
class DownloadedResource:
    url: str
    content_type: str
    content: bytes
    ssl_compatibility_fallback: bool = False


@dataclass(frozen=True)
class ExtractedResourceContent:
    """保留合併文字、逐頁證據與原始文件雜湊。"""

    text: str
    document_hash: str
    pages: tuple[DocumentPageEvidence, ...] = tuple()


class AnnouncementDetailFetcher:
    """下載公告正文與附件，以結構化狀態保存解析結果。"""

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

    def fetch_text(self, scholarship: Scholarship) -> str:
        return self._fetch_result(scholarship).text

    def fetch_with_diagnostics(self, scholarship: Scholarship) -> DetailFetchResult:
        try:
            return self._fetch_result(scholarship)
        except Exception as error:
            return self._source_failure(scholarship.source_url, error)

    def _fetch_result(self, scholarship: Scholarship) -> DetailFetchResult:
        with DetailSafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            requested_url = scholarship.source_url
            resource = self._download(client, requested_url)
            kind = detect_document_kind(resource.content_type, resource.url)
            if kind != "unsupported":
                return self._direct_document_result(
                    resource,
                    kind,
                    requested_url,
                    scholarship.title,
                )
            if not self._is_html(resource):
                raise ValueError("來源不是支援文件或 HTML")
            return self._html_result(client, resource, scholarship.title, requested_url)

    def _direct_document_result(
        self,
        resource: DownloadedResource,
        kind: str,
        requested_url: str,
        title: str,
    ) -> DetailFetchResult:
        content = self._document_content(resource)
        source = self._success_diagnostic(
            "source",
            requested_url,
            resource,
            kind,
            content,
        )
        if not content_matches_announcement(title, content.text):
            return self._content_mismatch_result(source, content.text)
        return DetailFetchResult(
            content.text,
            source,
            tuple(),
            0,
            body_text=content.text,
            extracted_attachments=tuple(),
            rules_status=RULES_STATUS_NOT_REQUIRED,
        )

    def _html_result(
        self,
        client: DetailSafeHttpClient,
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
            self._attachment_result(
                client,
                url,
                inventory.role_at(index),
                inventory.label_at(index),
            )
            for index, url in enumerate(inventory.selected_urls)
        ]
        diagnostics = tuple(diagnostic for _, diagnostic in results)
        extracted_attachments = tuple(
            self._build_extracted_attachment(content, diagnostic)
            for content, diagnostic in results
        )
        rules_texts = [
            item.text
            for item in extracted_attachments
            if item.status == "success" and item.content_role == CONTENT_RULES
        ]
        rules_status = self._determine_rules_status(body, inventory, extracted_attachments)
        body_content = self._html_content(resource, body)
        source = self._success_diagnostic(
            "source",
            requested_url,
            resource,
            "html",
            body_content,
        )
        if not content_matches_announcement(title, body, rules_texts):
            return self._content_mismatch_result(
                source,
                body,
                diagnostics,
                inventory.discovered_count,
                extracted_attachments,
                rules_status,
            )
        return DetailFetchResult(
            self._combine_text(body, rules_texts),
            source,
            diagnostics,
            inventory.discovered_count,
            body_text=body,
            extracted_attachments=extracted_attachments,
            rules_status=rules_status,
        )

    def _content_mismatch_result(
        self,
        source: ResourceDiagnostic,
        body_text: str,
        attachments: tuple[ResourceDiagnostic, ...] = tuple(),
        discovered_attachment_count: int = 0,
        extracted_attachments: tuple[ExtractedAttachment, ...] = tuple(),
        rules_status: str = RULES_STATUS_UNKNOWN,
    ) -> DetailFetchResult:
        mismatch = replace(
            source,
            status="error",
            error="ContentMismatchError: 公告正文與標題或申請語境不相符",
        )
        return DetailFetchResult(
            "",
            mismatch,
            attachments,
            discovered_attachment_count,
            body_text=body_text,
            extracted_attachments=extracted_attachments,
            rules_status=rules_status,
        )

    def _build_extracted_attachment(
        self,
        content: ExtractedResourceContent,
        diagnostic: ResourceDiagnostic,
    ) -> ExtractedAttachment:
        content_role = (
            classify_attachment_content(content.text, diagnostic.attachment_role)
            if diagnostic.status == "success"
            else "uncertain"
        )
        verification_status = (
            "parsed_with_page_evidence"
            if diagnostic.status == "success" and content.pages
            else "parsed"
            if diagnostic.status == "success"
            else "unresolved"
        )
        return ExtractedAttachment(
            requested_url=diagnostic.requested_url,
            final_url=diagnostic.final_url,
            label=diagnostic.attachment_label,
            role_hint=diagnostic.attachment_role,
            content_role=content_role,
            document_kind=diagnostic.document_kind,
            status=diagnostic.status,
            text=content.text,
            error=diagnostic.error,
            document_hash=content.document_hash,
            pages=content.pages,
            verification_status=verification_status,
        )

    def _determine_rules_status(
        self,
        body_text: str,
        inventory: AttachmentLinkInventory,
        attachments: tuple[ExtractedAttachment, ...],
    ) -> str:
        if any(
            item.status == "success" and item.content_role == CONTENT_RULES
            for item in attachments
        ):
            return RULES_STATUS_RESOLVED

        requirement = detect_attachment_requirement(body_text)
        if requirement.required and inventory.discovered_count == 0:
            return RULES_STATUS_DECLARED_MISSING
        if inventory.discovered_rules_count > 0:
            return RULES_STATUS_DISCOVERED_UNRESOLVED
        if inventory.discovered_generic_count > 0:
            return RULES_STATUS_GENERIC_UNCONFIRMED
        if requirement.required:
            return RULES_STATUS_DISCOVERED_UNRESOLVED
        if inventory.discovered_count > 0 and not any(
            item.status == "success" for item in attachments
        ):
            return RULES_STATUS_DISCOVERED_UNRESOLVED
        return RULES_STATUS_NOT_REQUIRED

    def _attachment_result(
        self,
        client: DetailSafeHttpClient,
        requested_url: str,
        attachment_role: str = "unknown",
        attachment_label: str = "",
    ) -> tuple[ExtractedResourceContent, ResourceDiagnostic]:
        resource: DownloadedResource | None = None
        kind = "unknown"
        try:
            resource = self._download(client, requested_url)
            kind = detect_document_kind(resource.content_type, resource.url)
            content = self._resource_content(resource, kind)
            return content, self._success_diagnostic(
                "attachment",
                requested_url,
                resource,
                kind,
                content,
                attachment_role,
                attachment_label,
            )
        except Exception as error:
            return self._empty_content(), self._error_diagnostic(
                requested_url,
                resource,
                kind,
                error,
                attachment_role,
                attachment_label,
            )

    def _resource_content(
        self,
        resource: DownloadedResource,
        kind: str,
    ) -> ExtractedResourceContent:
        if kind != "unsupported":
            return self._document_content(resource)
        if self._is_html(resource):
            text = extract_announcement_text(self._decode_html(resource), "", resource.url)
            return self._html_content(resource, text)
        raise ValueError("不支援的附件格式")

    def _success_diagnostic(
        self,
        role: str,
        requested_url: str,
        resource: DownloadedResource,
        kind: str,
        content: ExtractedResourceContent,
        attachment_role: str = "unknown",
        attachment_label: str = "",
    ) -> ResourceDiagnostic:
        return ResourceDiagnostic(
            role,
            requested_url,
            resource.url,
            resource.content_type,
            len(resource.content),
            kind,
            "success",
            len(content.text),
            "",
            attachment_role,
            attachment_label,
            resource.ssl_compatibility_fallback,
            document_hash=content.document_hash,
            page_count=len(content.pages),
        )

    def _error_diagnostic(
        self,
        requested_url: str,
        resource: DownloadedResource | None,
        kind: str,
        error: Exception,
        attachment_role: str = "unknown",
        attachment_label: str = "",
    ) -> ResourceDiagnostic:
        return ResourceDiagnostic(
            "attachment",
            requested_url,
            resource.url if resource else "",
            resource.content_type if resource else "",
            len(resource.content) if resource else 0,
            kind,
            "error",
            0,
            self._error_text(error),
            attachment_role,
            attachment_label,
            bool(resource and resource.ssl_compatibility_fallback),
        )

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
        return DetailFetchResult(
            "",
            source,
            tuple(),
            0,
            body_text="",
            extracted_attachments=tuple(),
            rules_status=RULES_STATUS_UNKNOWN,
        )

    def _document_content(
        self,
        resource: DownloadedResource,
    ) -> ExtractedResourceContent:
        try:
            parsed = extract_document(
                resource.content,
                resource.content_type,
                resource.url,
                self.max_pdf_pages,
            )
        except Exception as parse_error:
            text = self._legacy_document_text(resource, parse_error)
            pages = (DocumentPageEvidence(1, text),) if text.strip() else tuple()
            return ExtractedResourceContent(
                text,
                self._content_hash(resource.content),
                pages,
            )
        return ExtractedResourceContent(
            parsed.text,
            self._content_hash(resource.content),
            parsed.pages,
        )

    # 保留舊測試與客製擷取器替換點；正式解析失敗仍維持 fail closed。
    def _legacy_document_text(
        self,
        resource: DownloadedResource,
        parse_error: Exception,
    ) -> str:
        try:
            return extract_document_text(
                resource.content,
                resource.content_type,
                resource.url,
                self.max_pdf_pages,
            )
        except Exception:
            raise parse_error

    def _html_content(
        self,
        resource: DownloadedResource,
        text: str,
    ) -> ExtractedResourceContent:
        pages = (
            (DocumentPageEvidence(1, text, EXTRACTION_HTML_TEXT),)
            if text.strip()
            else tuple()
        )
        return ExtractedResourceContent(
            text,
            self._content_hash(resource.content),
            pages,
        )

    def _empty_content(self) -> ExtractedResourceContent:
        return ExtractedResourceContent("", "")

    def _content_hash(self, content: bytes) -> str:
        return sha256(content).hexdigest()

    def _download(self, client: DetailSafeHttpClient, url: str) -> DownloadedResource:
        with client.stream(url) as (response, fallback):
            response.raise_for_status()
            self._validate_content_length(response)
            content = self._read_limited(response)
            return DownloadedResource(
                str(response.url),
                response.headers.get("Content-Type", ""),
                content,
                fallback,
            )

    def _validate_content_length(self, response: httpx.Response) -> None:
        raw_length = response.headers.get("Content-Length", "0")
        if raw_length.isdigit() and int(raw_length) > self.max_download_bytes:
            raise ValueError("下載檔案超過安全上限")

    def _read_limited(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > self.max_download_bytes:
                raise ValueError("下載檔案超過安全上限")
            chunks.append(chunk)
        return b"".join(chunks)

    def _is_html(self, resource: DownloadedResource) -> bool:
        content_type = resource.content_type.lower()
        prefix = resource.content.lstrip()[:20].lower()
        return "text/html" in content_type or prefix.startswith((b"<!doctype", b"<html"))

    def _decode_html(self, resource: DownloadedResource) -> str:
        match = re.search(r"charset=([^;\s]+)", resource.content_type, re.IGNORECASE)
        encoding = match.group(1).strip('"\'') if match else "utf-8"
        return resource.content.decode(encoding, errors="replace")

    def _combine_text(self, body: str, attachment_texts: list[str]) -> str:
        return "\n".join([body, *(text for text in attachment_texts if text.strip())])

    def _parse_text(self, html: str, title: str = "", source_url: str = "") -> str:
        return extract_announcement_text(html, title, source_url)

    def _error_text(self, error: Exception) -> str:
        return f"{type(error).__name__}: {' '.join(str(error).split())}"[:240]
