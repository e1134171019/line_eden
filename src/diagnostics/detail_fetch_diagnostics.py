# -*- coding: utf-8 -*-

from dataclasses import dataclass


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


@dataclass(frozen=True)
class DetailFetchResult:
    """公告正文、附件與完整擷取診斷結果。"""

    text: str
    source: ResourceDiagnostic
    attachments: tuple[ResourceDiagnostic, ...]
    discovered_attachment_count: int

    # 統計成功解析的附件數量。
    def successful_attachment_count(self) -> int:
        return sum(item.status == "success" for item in self.attachments)

    # 統計未成功解析的附件數量。
    def failed_attachment_count(self) -> int:
        return sum(item.status != "success" for item in self.attachments)

    # 統計成功解析且可作為主要資格辦法的附件數量。
    def successful_rules_count(self) -> int:
        return sum(
            item.status == "success" and item.attachment_role == "rules"
            for item in self.attachments
        )
