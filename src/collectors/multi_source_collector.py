# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re
import unicodedata

from src.collectors.base_collector import BaseCollector
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


class MultiSourceCollector(BaseCollector):
    """依序執行多個來源，隔離單站錯誤並輸出可稽核診斷。"""

    def __init__(self, collectors: list[BaseCollector]) -> None:
        if not collectors:
            raise ValueError("MultiSourceCollector 至少需要一個來源。")
        self.collectors = collectors
        self.failures: list[CollectorFailure] = []
        self.diagnostics: list[SourceDiagnostic] = []

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
            except Exception as error:  # 單站故障不得拖垮其他來源。
                message = _safe_error(error)
                self.failures.append(CollectorFailure(source, message))
                self.diagnostics.append(
                    SourceDiagnostic(source, "error", 0, 0, 0, message)
                )
                continue

            successful_sources += 1
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
            self.diagnostics.append(
                SourceDiagnostic(
                    source,
                    "success",
                    len(collected),
                    accepted,
                    duplicates,
                )
            )

        if successful_sources == 0:
            details = "; ".join(
                f"{failure.source}: {failure.error}" for failure in self.failures
            )
            raise RuntimeError(f"五個官方來源全部失敗：{details}")
        if not records:
            raise RuntimeError("官方來源可連線，但沒有解析到任何獎助學金公告。")
        return records

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        for item in self.diagnostics:
            if item.status == "error":
                lines.append(f"{item.source}：失敗（{item.error}）")
                continue
            suffix = f"，跨站重複 {item.duplicate_count} 筆" if item.duplicate_count else ""
            lines.append(
                f"{item.source}：讀取 {item.collected_count} 筆，保留 {item.accepted_count} 筆{suffix}"
            )
        return lines


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


def _safe_error(error: Exception) -> str:
    text = " ".join(str(error).split())
    return text[:300] or type(error).__name__
