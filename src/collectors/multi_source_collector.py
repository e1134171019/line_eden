# -*- coding: utf-8 -*-

from dataclasses import dataclass

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship, build_dedup_hash


@dataclass(frozen=True)
class CollectorSource:
    code: str
    name: str
    collector: BaseCollector


@dataclass(frozen=True)
class CollectorDiagnostic:
    code: str
    name: str
    status: str
    collected_count: int
    error: str = ""


class MultiSourceCollector(BaseCollector):
    """依優先順序整合多個官方來源，單一來源失敗不拖垮其餘來源。"""

    def __init__(self, sources: list[CollectorSource]) -> None:
        if not sources:
            raise ValueError("MultiSourceCollector 至少需要一個來源")
        codes = [source.code for source in sources]
        if len(codes) != len(set(codes)):
            raise ValueError("官方來源 code 不得重複")
        self.sources = tuple(sources)
        self.last_diagnostics: tuple[CollectorDiagnostic, ...] = tuple()

    def collect(self) -> list[Scholarship]:
        diagnostics: list[CollectorDiagnostic] = []
        merged: list[Scholarship] = []
        seen_dedup_hashes: set[str] = set()
        successful_sources = 0

        for source in self.sources:
            try:
                records = source.collector.collect()
            except Exception as error:  # noqa: BLE001 - 必須隔離外部來源錯誤
                diagnostics.append(
                    CollectorDiagnostic(
                        source.code,
                        source.name,
                        "error",
                        0,
                        self._safe_error(error),
                    )
                )
                continue

            successful_sources += 1
            accepted = 0
            for item in records:
                dedup_hash = item.dedup_hash or build_dedup_hash(item.title)
                if dedup_hash in seen_dedup_hashes:
                    continue
                seen_dedup_hashes.add(dedup_hash)
                merged.append(item)
                accepted += 1
            diagnostics.append(
                CollectorDiagnostic(source.code, source.name, "success", accepted)
            )

        self.last_diagnostics = tuple(diagnostics)
        if successful_sources == 0:
            details = "; ".join(
                f"{item.code}: {item.error}" for item in diagnostics if item.error
            )
            raise RuntimeError(f"全部官方來源蒐集失敗：{details}")
        return merged

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        for item in self.last_diagnostics:
            if item.status == "success":
                lines.append(f"{item.name}：成功 {item.collected_count} 筆")
            else:
                lines.append(f"{item.name}：失敗（{item.error}）")
        return lines

    def _safe_error(self, error: Exception) -> str:
        text = " ".join(str(error).split()).strip()
        return text[:160] or error.__class__.__name__
