# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re
import unicodedata

from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectorDiagnostic
from src.models.scholarship import Scholarship

_GENERIC_TITLES = {
    "獎學金",
    "助學金",
    "獎助學金",
    "獎學金公告",
    "助學金公告",
    "獎助學金公告",
    "申請公告",
}
_COMPLETENESS_LABELS = {
    "complete": "完整",
    "partial": "部分完成",
    "incremental": "增量",
    "failed": "失敗",
    "unknown": "完整性未知",
}


@dataclass(frozen=True)
class CollectorFailure:
    source: str
    error: str


@dataclass(frozen=True)
class SourceDiagnostic:
    source: str
    status: str
    collected_count: int
    accepted_count: int
    duplicate_count: int
    error: str = ""
    completeness: str = "unknown"
    pages_detected: int | None = None
    pages_requested: int = 0
    pages_succeeded: int = 0
    raw_rows: int = 0
    parsed_rows: int = 0
    rejected_rows: int = 0
    stop_reason: str = ""
    ssl_compatibility_fallback: bool = False
    child_sources_detected: int = 0
    child_sources_succeeded: int = 0


class MultiSourceCollector(BaseCollector):
    """依序執行多個來源，隔離單站錯誤並輸出可稽核完整性。"""

    def __init__(self, collectors: list[BaseCollector]) -> None:
        if not collectors:
            raise ValueError("MultiSourceCollector 至少需要一個來源。")
        self.collectors = collectors
        self.failures: list[CollectorFailure] = []
        self.diagnostics: list[SourceDiagnostic] = []

    # 執行所有來源並跨站去重。
    def collect(self) -> list[Scholarship]:
        self.failures = []
        self.diagnostics = []
        records: list[Scholarship] = []
        seen: set[str] = set()
        successful_sources = 0
        for collector in self.collectors:
            source = _collector_label(collector)
            try:
                collected = collector.collect()
            except Exception as error:
                self._record_failure(source, collector, error)
                continue
            successful_sources += 1
            accepted, duplicates = self._append_unique(records, seen, collected)
            self.diagnostics.append(
                self._build_diagnostic(source, collector, collected, accepted, duplicates)
            )
        self._validate_collection(successful_sources, records)
        return records

    # 將來源數、公告數與完整性分開呈現。
    def summary_lines(self) -> list[str]:
        lines = [self._health_line()]
        for item in self.diagnostics:
            if item.status == "error":
                lines.append(f"{item.source}：失敗（{item.error}）")
                continue
            if item.status == "empty":
                lines.append(f"{item.source}：可連線，但解析 0 筆")
                continue
            lines.append(self._source_line(item))
        return lines

    # 合併 collector 自身診斷與跨站去重結果。
    def _build_diagnostic(
        self,
        source: str,
        collector: BaseCollector,
        collected: list[Scholarship],
        accepted: int,
        duplicates: int,
    ) -> SourceDiagnostic:
        detail = _collector_diagnostic(collector)
        status = "empty" if not collected else "success"
        if detail.completeness == "partial" and collected:
            status = "partial"
        return SourceDiagnostic(
            source=source,
            status=status,
            collected_count=len(collected),
            accepted_count=accepted,
            duplicate_count=duplicates,
            error=detail.error,
            completeness=detail.completeness,
            pages_detected=detail.pages_detected,
            pages_requested=detail.pages_requested,
            pages_succeeded=detail.pages_succeeded,
            raw_rows=detail.raw_rows,
            parsed_rows=detail.parsed_rows,
            rejected_rows=detail.rejected_rows,
            stop_reason=detail.stop_reason,
            ssl_compatibility_fallback=detail.ssl_compatibility_fallback,
            child_sources_detected=detail.child_sources_detected,
            child_sources_succeeded=detail.child_sources_succeeded,
        )

    # 記錄單一來源錯誤，不讓例外中斷其餘來源。
    def _record_failure(
        self,
        source: str,
        collector: BaseCollector,
        error: Exception,
    ) -> None:
        message = _safe_error(error)
        detail = _collector_diagnostic(collector)
        self.failures.append(CollectorFailure(source, message))
        self.diagnostics.append(
            SourceDiagnostic(
                source,
                "error",
                0,
                0,
                0,
                message,
                completeness="failed",
                pages_detected=detail.pages_detected,
                pages_requested=detail.pages_requested,
                pages_succeeded=detail.pages_succeeded,
                raw_rows=detail.raw_rows,
                parsed_rows=detail.parsed_rows,
                rejected_rows=detail.rejected_rows,
                stop_reason=detail.stop_reason,
                ssl_compatibility_fallback=detail.ssl_compatibility_fallback,
                child_sources_detected=detail.child_sources_detected,
                child_sources_succeeded=detail.child_sources_succeeded,
            )
        )

    # 將單一來源結果跨站去重後加入總清單。
    def _append_unique(
        self,
        records: list[Scholarship],
        seen: set[str],
        collected: list[Scholarship],
    ) -> tuple[int, int]:
        accepted = 0
        duplicates = 0
        for item in collected:
            key = build_cross_source_key(item)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            records.append(item)
            accepted += 1
        return accepted, duplicates

    # 來源全部失敗或全部空結果時採 fail closed。
    def _validate_collection(
        self,
        successful_sources: int,
        records: list[Scholarship],
    ) -> None:
        if successful_sources == 0:
            details = "; ".join(
                f"{failure.source}: {failure.error}" for failure in self.failures
            )
            raise RuntimeError(f"五個官方來源全部失敗：{details}")
        if not records:
            raise RuntimeError("官方來源可連線，但沒有解析到任何獎助學金公告。")

    # 彙整設定來源、產出資料來源、空結果、部分完成與失敗數量。
    def _health_line(self) -> str:
        configured = len(self.collectors)
        producing = sum(item.status in {"success", "partial"} for item in self.diagnostics)
        empty = sum(item.status == "empty" for item in self.diagnostics)
        partial = sum(item.status == "partial" for item in self.diagnostics)
        failed = sum(item.status == "error" for item in self.diagnostics)
        health = "正常" if producing == configured and partial == 0 else "降級"
        return (
            f"來源網站：設定 {configured}，成功產生資料 {producing}，"
            f"空結果 {empty}，部分完成 {partial}，失敗 {failed}；整體：{health}"
        )

    # 建立單一來源的人類可讀完整性摘要。
    def _source_line(self, item: SourceDiagnostic) -> str:
        parts = [f"{item.source}：{_COMPLETENESS_LABELS.get(item.completeness, item.completeness)}"]
        if item.pages_detected is not None and item.pages_requested:
            parts.append(f"頁面 {item.pages_succeeded}/{item.pages_detected}")
        if item.child_sources_detected:
            parts.append(
                f"子來源 {item.child_sources_succeeded}/{item.child_sources_detected}"
            )
        if item.raw_rows:
            parts.append(
                f"原始列 {item.raw_rows}，解析 {item.parsed_rows}，排除 {item.rejected_rows}"
            )
        parts.append(f"跨來源去重後保留 {item.accepted_count}/{item.collected_count} 筆")
        if item.ssl_compatibility_fallback:
            parts.append("SSL 相容重試")
        if item.stop_reason:
            parts.append(f"停止：{item.stop_reason}")
        return "；".join(parts)


def build_cross_source_key(item: Scholarship) -> str:
    """建立跨來源鍵；具名公告忽略轉載日期，泛稱公告保留日期。"""
    title = _normalize_title(item.title)
    if title in _GENERIC_TITLES:
        return f"{title}|{item.published_date.strip()}"
    return title


def _normalize_title(title: str) -> str:
    value = unicodedata.normalize("NFKC", " ".join(title.split())).casefold()
    value = re.sub(r"^[【〖\[][^】〗\]]{1,24}[】〗\]]\s*", "", value)
    value = re.sub(
        r"^(?:轉知|公告|重要資訊|最新消息|有關|函轉|教育部公告)+[：:－\-｜|\s]*",
        "",
        value,
    )
    return re.sub(r"[\W_]+", "", value)


def _collector_label(collector: BaseCollector) -> str:
    label = getattr(collector, "source_label", "")
    if isinstance(label, str) and label.strip():
        return label.strip()
    config = getattr(collector, "config", None)
    display_name = getattr(config, "display_name", "")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()
    source_name = getattr(config, "source_name", "")
    if isinstance(source_name, str) and source_name.strip():
        return source_name.strip()
    return type(collector).__name__


def _collector_diagnostic(collector: BaseCollector) -> CollectorDiagnostic:
    value = getattr(collector, "diagnostic", None)
    return value if isinstance(value, CollectorDiagnostic) else CollectorDiagnostic()


def _safe_error(error: Exception) -> str:
    text = " ".join(str(error).split())
    return text[:300] or type(error).__name__
