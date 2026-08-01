# -*- coding: utf-8 -*-

from collections import deque
from dataclasses import dataclass, replace
import re

import httpx

from config import ATTACHMENT_FOLLOW_MAX_DEPTH, DOCUMENT_TEXT_EXTRACTION_VERSION

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
from src.extractors.announcement_content_extractor import (
    extract_announcement_content,
    extract_announcement_text,
)
from src.extractors.announcement_relevance import content_matches_announcement
from src.extractors.attachment_content_classifier import (
    CONTENT_RULES,
    classify_attachment_content,
)
from src.extractors.attachment_link_extractor import (
    AttachmentLinkInventory,
    GENERIC_ATTACHMENT,
    RULES,
    UNRELATED,
    extract_attachment_inventory,
)
from src.extractors.document_text_extractor import detect_document_kind, extract_document_text
from src.models.detail_extraction import build_named_extraction_hash
from src.models.scholarship import Scholarship


@dataclass(frozen=True)
class DownloadedResource:
    url: str
    content_type: str
    content: bytes
    ssl_compatibility_fallback: bool = False


@dataclass(frozen=True)
class AttachmentGraphResult:
    """保存附件圖下載結果與跨頁發現統計。"""

    resources: tuple[tuple[str, ResourceDiagnostic], ...]
    discovered_count: int
    discovered_rules_count: int
    discovered_generic_count: int


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
        text = self._document_text(resource)
        policy_name = f"document-{kind}"
        policy_hash = build_named_extraction_hash(
            policy_name,
            DOCUMENT_TEXT_EXTRACTION_VERSION,
            (f"max_pdf_pages={self.max_pdf_pages}",),
        )
        source = self._success_diagnostic(
            "source",
            requested_url,
            resource,
            kind,
            text,
            extraction_policy_name=policy_name,
            extraction_policy_hash=policy_hash,
        )
        if not content_matches_announcement(title, text):
            return self._content_mismatch_result(source, text)
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
        client: DetailSafeHttpClient,
        resource: DownloadedResource,
        title: str,
        requested_url: str,
    ) -> DetailFetchResult:
        html = self._decode_html(resource)
        extracted_body = extract_announcement_content(html, title, resource.url)
        body = extracted_body.text
        inventory = extract_attachment_inventory(
            html,
            resource.url,
            title,
            self.max_attachment_count,
        )
        graph = self._fetch_attachment_graph(client, inventory, title)
        results = list(graph.resources)
        inventory = replace(
            inventory,
            discovered_count=graph.discovered_count,
            discovered_rules_count=graph.discovered_rules_count,
            discovered_generic_count=graph.discovered_generic_count,
        )
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
        rules_status = self._determine_rules_status(body, inventory, extracted_attachments)
        source = self._success_diagnostic(
            "source",
            requested_url,
            resource,
            "html",
            body,
            extraction_policy_name=extracted_body.policy_name,
            extraction_policy_hash=extracted_body.policy_hash,
            selector_used=extracted_body.selector_used,
            extraction_fallback=extracted_body.used_fallback,
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

    def _fetch_attachment_graph(
        self,
        client: DetailSafeHttpClient,
        inventory: AttachmentLinkInventory,
        title: str,
    ) -> AttachmentGraphResult:
        """副作用函式：最多追蹤兩層附件頁，並限制總下載數。"""

        queue = _attachment_queue(inventory)
        visited: set[str] = set()
        resources: list[tuple[str, ResourceDiagnostic]] = []
        discovered = inventory.discovered_count
        rules_count = inventory.discovered_rules_count
        generic_count = inventory.discovered_generic_count
        while queue and len(resources) < self.max_attachment_count:
            url, role, label, depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            text, diagnostic, nested_html = self._attachment_node(client, url, role, label)
            resources.append((text, diagnostic))
            if not nested_html or depth >= ATTACHMENT_FOLLOW_MAX_DEPTH:
                continue
            nested = extract_attachment_inventory(
                nested_html,
                diagnostic.final_url or url,
                title,
                self.max_attachment_count - len(resources),
            )
            discovered += nested.discovered_count
            rules_count += nested.discovered_rules_count
            generic_count += nested.discovered_generic_count
            _enqueue_nested_attachments(queue, nested, role, depth + 1, visited)
        return AttachmentGraphResult(
            tuple(resources), discovered, rules_count, generic_count
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
    ) -> tuple[str, ResourceDiagnostic]:
        text, diagnostic, _ = self._attachment_node(
            client,
            requested_url,
            attachment_role,
            attachment_label,
        )
        return text, diagnostic

    def _attachment_node(
        self,
        client: DetailSafeHttpClient,
        requested_url: str,
        attachment_role: str,
        attachment_label: str,
    ) -> tuple[str, ResourceDiagnostic, str]:
        """副作用函式：下載一個附件節點，HTML 節點保留給下一層探索。"""

        resource: DownloadedResource | None = None
        kind = "unknown"
        try:
            resource = self._download(client, requested_url)
            kind = detect_document_kind(resource.content_type, resource.url)
            nested_html = self._decode_html(resource) if self._is_html(resource) else ""
            try:
                text = self._resource_text(resource, kind)
            except ValueError as error:
                if not nested_html:
                    raise
                diagnostic = self._error_diagnostic(
                    requested_url,
                    resource,
                    kind,
                    error,
                    attachment_role,
                    attachment_label,
                )
                return "", diagnostic, nested_html
            diagnostic = self._success_diagnostic(
                "attachment",
                requested_url,
                resource,
                kind,
                text,
                attachment_role,
                attachment_label,
            )
            return text, diagnostic, nested_html
        except Exception as error:
            diagnostic = self._error_diagnostic(
                requested_url,
                resource,
                kind,
                error,
                attachment_role,
                attachment_label,
            )
            return "", diagnostic, ""

    def _resource_text(self, resource: DownloadedResource, kind: str) -> str:
        if kind != "unsupported":
            return self._document_text(resource)
        if self._is_html(resource):
            return extract_announcement_text(self._decode_html(resource), "", resource.url)
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
        extraction_policy_name: str = "",
        extraction_policy_hash: str = "",
        selector_used: str = "",
        extraction_fallback: bool = False,
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
            resource.ssl_compatibility_fallback,
            extraction_policy_name,
            extraction_policy_hash,
            selector_used,
            extraction_fallback,
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

    def _error_text(self, error: Exception) -> str:
        return f"{type(error).__name__}: {' '.join(str(error).split())}"[:240]

    def _document_text(self, resource: DownloadedResource) -> str:
        return extract_document_text(
            resource.content,
            resource.content_type,
            resource.url,
            self.max_pdf_pages,
        )

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


AttachmentQueue = deque[tuple[str, str, str, int]]


def _attachment_queue(inventory: AttachmentLinkInventory) -> AttachmentQueue:
    """純函式：將第一層附件清單轉成有深度資訊的佇列。"""

    return deque(
        (
            url,
            inventory.role_at(index),
            inventory.label_at(index),
            0,
        )
        for index, url in enumerate(inventory.selected_urls)
    )


def _enqueue_nested_attachments(
    queue: AttachmentQueue,
    inventory: AttachmentLinkInventory,
    parent_role: str,
    depth: int,
    visited: set[str],
) -> None:
    """副作用函式：將中介頁找到的下一層文件加入有限佇列。"""

    for index, url in enumerate(inventory.selected_urls):
        if url in visited:
            continue
        role = _inherit_attachment_role(inventory.role_at(index), parent_role)
        queue.append((url, role, inventory.label_at(index), depth))


def _inherit_attachment_role(role: str, parent_role: str) -> str:
    """純函式：中介頁的泛稱下載連結繼承上一層辦法角色。"""

    if role in {UNRELATED, GENERIC_ATTACHMENT} and parent_role == RULES:
        return RULES
    return role
