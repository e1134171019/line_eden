# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

import httpx

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
from src.extractors.attachment_content_classifier import (
    CONTENT_RULES,
    classify_attachment_content,
)
from src.extractors.attachment_link_extractor import (
    AttachmentLinkInventory,
    extract_attachment_inventory,
)
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
        headers = {"User-Agent": self.user_agent}
        with httpx.Client(
            headers=headers,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        ) as client:
            requested_url = scholarship.source_url
            resource = self._download(client, requested_url)
            kind = detect_document_kind(resource.content_type, resource.url)
            if kind != "unsupported":
                return self._direct_document_result(resource, kind, requested_url)
            if not self._is_html(resource):
                raise ValueError("來源不是支援文件或 HTML")
            return self._html_result(client, resource, scholarship.title, requested_url)

    def _direct_document_result(
        self,
        resource: DownloadedResource,
        kind: str,
        requested_url: str,
    ) -> DetailFetchResult:
        text = self._document_text(resource)
        source = self._success_diagnostic("source", requested_url, resource, kind, text)
        return DetailFetchResult(
            text,
            source,
            tuple(),
            0,
            body_text=text,
            extracted_attachments=tuple(),
            rules_status=RULES_STATUS_NOT_REQUIRED,
        )

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
            self._build_extracted_attachment(text, diagnostic)
            for text, diagnostic in results
        )
        rules_texts = [
            item.text
            for item in extracted_attachments
            if item.status == "success" and item.content_role == CONTENT_RULES
        ]
        rules_status = self._determine_rules_status(
            body,
            inventory,
            extracted_attachments,
        )
        source = self._success_diagnostic("source", requested_url, resource, "html", body)
        combined = self._combine_text(body, rules_texts)
        return DetailFetchResult(
            combined,
            source,
            diagnostics,
            inventory.discovered_count,
            body_text=body,
            extracted_attachments=extracted_attachments,
            rules_status=rules_status,
        )

    def _build_extracted_attachment(
        self,
        text: str,
        diagnostic: ResourceDiagnostic,
    ) -> ExtractedAttachment:
        content_role = (
            classify_attachment_content(text, diagnostic.attachment_role)
            if diagnostic.status == "success"
            else "uncertain"
        )
        return ExtractedAttachment(
            requested_url=diagnostic.requested_url,
            final_url=diagnostic.final_url,
            label=diagnostic.attachment_label,
            role_hint=diagnostic.attachment_role,
            content_role=content_role,
            document_kind=diagnostic.document_kind,
            status=diagnostic.status,
            text=text,
            error=diagnostic.error,
        )

    def _determine_rules_status(
        self,
        body_text: str,
        inventory: AttachmentLinkInventory,
        attachments: tuple[ExtractedAttachment, ...],
    ) -> str:
        resolved = any(
            item.status == "success" and item.content_role == CONTENT_RULES
            for item in attachments
        )
        if resolved:
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
        client: httpx.Client,
        requested_url: str,
        attachment_role: str = "unknown",
        attachment_label: str = "",
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
                attachment_label,
            )
            return text, diagnostic
        except Exception as error:
            return "", self._error_diagnostic(
                requested_url,
                resource,
                kind,
                error,
                attachment_role,
                attachment_label,
            )

    def _resource_text(self, resource: DownloadedResource, kind: str) -> str:
        if kind != "unsupported":
            return self._document_text(resource)
        if self._is_html(resource):
            html = self._decode_html(resource)
            return extract_announcement_text(html, "", resource.url)
        raise ValueError("不支援的附件格式")

    def _success_diagnostic(
        self,
        role: str,
        requested_url: str,
        resource: DownloadedResource,
        kind: str,
        text: str,
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
            len(text),
            "",
            attachment_role,
            attachment_label,
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
            attachment_label,
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

    def _error_text(self, error: Exception) -> str:
        message = " ".join(str(error).split())
        return f"{type(error).__name__}: {message}"[:240]

    def _document_text(self, resource: DownloadedResource) -> str:
        return extract_document_text(
            resource.content,
            resource.content_type,
            resource.url,
            self.max_pdf_pages,
        )

    def _download(self, client: httpx.Client, url: str) -> DownloadedResource:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            self._validate_content_length(response)
            content = self._read_limited(response)
            content_type = response.headers.get("Content-Type", "")
            return DownloadedResource(str(response.url), content_type, content)

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
