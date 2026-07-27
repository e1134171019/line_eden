# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship


@dataclass(frozen=True)
class CollectorFailure:
    source: str
    error: str


class MultiSourceCollector(BaseCollector):
    """依序執行多個來源，單一來源失敗時保留其他來源結果。"""

    def __init__(self, collectors: list[BaseCollector]) -> None:
        if not collectors:
            raise ValueError("MultiSourceCollector 至少需要一個來源。")
        self.collectors = collectors
        self.failures: list[CollectorFailure] = []

    def collect(self) -> list[Scholarship]:
        self.failures = []
        records: list[Scholarship] = []
        seen: set[str] = set()
        for collector in self.collectors:
            try:
                collected = collector.collect()
            except Exception as error:  # 單站故障不得拖垮全部來源。
                self.failures.append(
                    CollectorFailure(type(collector).__name__, _safe_error(error))
                )
                continue
            for item in collected:
                key = build_cross_source_key(item)
                if key in seen:
                    continue
                seen.add(key)
                records.append(item)
        return records


def build_cross_source_key(item: Scholarship) -> str:
    """以標題與日期建立跨來源鍵，不把來源網址納入。"""
    title = re.sub(r"[\W_]+", "", item.title.casefold())
    date = item.published_date.strip()
    return f"{title}|{date}"


def _safe_error(error: Exception) -> str:
    text = " ".join(str(error).split())
    return text[:300] or type(error).__name__
