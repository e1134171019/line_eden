# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import StrEnum


class CollectionMode(StrEnum):
    """區分完整來源稽核與每日增量蒐集。"""

    FULL_AUDIT = "full_audit"
    INCREMENTAL = "incremental"


@dataclass(frozen=True)
class CollectorDiagnostic:
    """記錄單一來源是否完整抓取及解析結果。"""

    completeness: str = "unknown"
    pages_detected: int | None = None
    pages_requested: int = 0
    pages_succeeded: int = 0
    raw_rows: int = 0
    parsed_rows: int = 0
    rejected_rows: int = 0
    stop_reason: str = ""
    error: str = ""
    ssl_compatibility_fallback: bool = False
    child_sources_detected: int = 0
    child_sources_succeeded: int = 0
