# -*- coding: utf-8 -*-

from dataclasses import dataclass

RULES_STATUS_UNKNOWN = "unknown"
RULES_STATUS_NOT_REQUIRED = "not_required"
RULES_STATUS_RESOLVED = "resolved"
RULES_STATUS_DECLARED_MISSING = "declared_but_missing"
RULES_STATUS_DISCOVERED_UNRESOLVED = "discovered_but_unresolved"
RULES_STATUS_GENERIC_UNCONFIRMED = "generic_document_unconfirmed"


@dataclass(frozen=True)
class ResourceDiagnostic:
    """單一來源或附件的下載與文字解析診斷。"""

    role: str
    requested_url: str
    final_url: str
    content_type: str
    size_bytes: int
    document_kind: str
    status: str
    text_length: int
    error: str = ""
    attachment_role: str = "unknown"
    attachment_label: str = ""


@dataclass(frozen=True)
class ExtractedAttachment:
    """保留附件文字、角色提示與內容確認結果。"""

    requested_url: str
    final_url: str
    label: str
    role_hint: str
    content_role: str
    document_kind: str
    status: str
    text: str
    error: str = ""


@dataclass(frozen=True)
class NoticeContent:
    """不依賴字串 marker 的公告正文與附件證據。"""

    main_text: str
    attachments: tuple[ExtractedAttachment, ...]
    rules_status: str


@dataclass(frozen=True)
class DetailFetchResult:
    """公告正文、結構化附件證據與完整擷取診斷結果。"""

    # text 暫時保留給 legacy evaluator；新程式必須優先使用 content。
    text: str
    source: ResourceDiagnostic
    attachments: tuple[ResourceDiagnostic, ...]
    discovered_attachment_count: int
    body_text: str = ""
    extracted_attachments: tuple[ExtractedAttachment, ...] = tuple()
    rules_status: str = RULES_STATUS_UNKNOWN

    @property
    def content(self) -> NoticeContent:
        return NoticeContent(
            main_text=self.body_text or self.text,
            attachments=self.extracted_attachments,
            rules_status=self.rules_status,
        )

    def successful_attachment_count(self) -> int:
        return sum(item.status == "success" for item in self.attachments)

    def failed_attachment_count(self) -> int:
        return sum(item.status != "success" for item in self.attachments)

    def successful_rules_count(self) -> int:
        if self.extracted_attachments:
            return sum(
                item.status == "success"
                and item.content_role == "scholarship_rules"
                for item in self.extracted_attachments
            )
        return sum(
            item.status == "success" and item.attachment_role == "rules"
            for item in self.attachments
        )
