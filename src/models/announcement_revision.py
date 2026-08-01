# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import Enum
import hashlib
import json


class RevisionObservationStatus(str, Enum):
    """資料庫觀察新 revision 後的狀態。"""

    NOT_FOUND = "not_found"
    INITIALIZED = "initialized"
    UNCHANGED = "unchanged"
    CHANGED = "changed"


@dataclass(frozen=True)
class RevisionAttachment:
    """會影響公告 revision 的穩定附件欄位。"""

    content_role: str
    document_kind: str
    status: str
    text: str


@dataclass(frozen=True)
class RevisionContent:
    """建立 revision hash 所需的純內容快照。"""

    main_text: str
    attachments: tuple[RevisionAttachment, ...]
    rules_status: str


@dataclass(frozen=True)
class AnnouncementRevision:
    """一則穩定公告目前觀察到的內容版本。"""

    announcement_id: str
    revision_hash: str
    extraction_policy_hash: str


@dataclass(frozen=True)
class RevisionObservation:
    """repository 寫入 revision 後回傳的不可變結果。"""

    status: RevisionObservationStatus
    previous_revision_hash: str = ""


def normalize_revision_text(text: str) -> str:
    """壓縮排版空白，避免純格式變動造成 revision。"""
    return " ".join(text.split()).strip()


def build_revision_hash(content: RevisionContent) -> str:
    """以正文、附件內容與辦法狀態建立 deterministic revision hash。"""
    attachments = sorted(
        (
            {
                "content_role": item.content_role.strip(),
                "document_kind": item.document_kind.strip(),
                "status": item.status.strip(),
                "text": normalize_revision_text(item.text),
            }
            for item in content.attachments
        ),
        key=lambda item: (
            item["content_role"],
            item["document_kind"],
            item["status"],
            item["text"],
        ),
    )
    payload = {
        "main_text": normalize_revision_text(content.main_text),
        "attachments": attachments,
        "rules_status": content.rules_status.strip(),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
