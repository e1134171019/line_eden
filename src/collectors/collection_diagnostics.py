# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse


class CollectionMode(StrEnum):
    """區分完整來源稽核與每日增量蒐集。"""

    FULL_AUDIT = "full_audit"
    INCREMENTAL = "incremental"


class SourceAccessMode(StrEnum):
    """區分直接下載、核心來源涵蓋與待確認監測目標。"""

    DIRECT = "direct"
    CORE_COVERED = "core_covered"
    PENDING = "pending"


class AccountingStatus(StrEnum):
    """區分資料列帳本是否完整、失衡或尚未啟用。"""

    BALANCED = "balanced"
    UNBALANCED = "unbalanced"
    UNTRACKED = "untracked"


@dataclass(frozen=True)
class RowAccounting:
    """保存來源原始列到 collector 輸出的守恆帳本。"""

    status: AccountingStatus = AccountingStatus.UNTRACKED
    raw_rows: int = 0
    parsed_rows: int = 0
    rejected_rows: int = 0
    duplicate_rows: int = 0
    emitted_rows: int = 0

    @property
    def accounted_rows(self) -> int:
        """純函式：加總所有有明確去向的來源資料列。"""

        return self.parsed_rows + self.rejected_rows + self.duplicate_rows

    @property
    def balance_delta(self) -> int:
        """純函式：回傳尚未被解析、排除或去重說明的列數。"""

        return self.raw_rows - self.accounted_rows

    @property
    def emission_delta(self) -> int:
        """純函式：回傳解析列與 collector 實際輸出筆數差異。"""

        return self.parsed_rows - self.emitted_rows


@dataclass(frozen=True)
class RejectionReasonCount:
    """保存被排除資料列的可稽核原因與數量。"""

    reason: str
    count: int


@dataclass(frozen=True)
class SourceTargetDiagnostic:
    """記錄一個邏輯監測目標的入口與蒐集結果。"""

    target_id: str
    display_name: str
    access_mode: SourceAccessMode
    entry_url: str = ""
    completeness: str = "unknown"
    pages_detected: int | None = None
    pages_requested: int = 0
    pages_succeeded: int = 0
    raw_rows: int = 0
    parsed_rows: int = 0
    rejected_rows: int = 0
    duplicate_rows: int = 0
    error: str = ""

    @property
    def domain(self) -> str:
        """純函式：回傳入口 URL 的小寫主機名稱。"""

        return (urlparse(self.entry_url).hostname or "").casefold()

    @property
    def is_succeeded(self) -> bool:
        """純函式：直接來源必須實際產生該方案公告，不能只看 HTTP 成功。"""

        if self.access_mode is SourceAccessMode.CORE_COVERED:
            return self.parsed_rows > 0 and self.completeness == "covered"
        return (
            self.pages_succeeded > 0
            and self.parsed_rows > 0
            and self.completeness not in {"failed", "partial"}
        )


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
    duplicate_rows: int = 0
    rejection_reasons: tuple[RejectionReasonCount, ...] = tuple()
    stop_reason: str = ""
    error: str = ""
    ssl_compatibility_fallback: bool = False
    child_sources_detected: int = 0
    child_sources_succeeded: int = 0
    target_diagnostics: tuple[SourceTargetDiagnostic, ...] = tuple()


def build_row_accounting(
    diagnostic: CollectorDiagnostic,
    emitted_rows: int,
) -> RowAccounting:
    """純函式：驗證原始列、解析、排除、來源內去重與輸出是否守恆。"""

    is_tracked = diagnostic.completeness != "unknown" or any(
        (
            diagnostic.pages_requested,
            diagnostic.raw_rows,
            diagnostic.parsed_rows,
            diagnostic.rejected_rows,
            diagnostic.duplicate_rows,
        )
    )
    if not is_tracked:
        return RowAccounting(emitted_rows=emitted_rows)
    is_balanced = (
        diagnostic.raw_rows
        == diagnostic.parsed_rows
        + diagnostic.rejected_rows
        + diagnostic.duplicate_rows
        and diagnostic.parsed_rows == emitted_rows
    )
    status = AccountingStatus.BALANCED if is_balanced else AccountingStatus.UNBALANCED
    return RowAccounting(
        status=status,
        raw_rows=diagnostic.raw_rows,
        parsed_rows=diagnostic.parsed_rows,
        rejected_rows=diagnostic.rejected_rows,
        duplicate_rows=diagnostic.duplicate_rows,
        emitted_rows=emitted_rows,
    )
