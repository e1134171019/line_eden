# -*- coding: utf-8 -*-

from src.collectors.base_collector import BaseCollector
from src.collectors.multi_source_collector import MultiSourceCollector
from src.models.scholarship import Scholarship


class StubCollector(BaseCollector):
    def __init__(self, source_label: str, items: list[Scholarship]) -> None:
        self.source_label = source_label
        self.items = items

    def collect(self) -> list[Scholarship]:
        return self.items


class BrokenCollector(BaseCollector):
    source_label = "故障來源"

    def collect(self) -> list[Scholarship]:
        raise RuntimeError("unavailable")


# 建立測試公告。
def _item() -> Scholarship:
    return Scholarship.from_raw(
        "fixture",
        "測試獎學金",
        "2026-07-28",
        "https://example.test/notice",
    )


# 部分來源空結果或失敗時，摘要必須明確標記降級。
def test_source_summary_reports_degraded_health() -> None:
    collector = MultiSourceCollector([
        StubCollector("有資料來源", [_item()]),
        StubCollector("空來源", []),
        BrokenCollector(),
    ])

    collector.collect()
    lines = collector.summary_lines()

    assert lines[0] == "來源健康：降級；設定 3，有資料 1，空結果 1，失敗 1"
    assert "空來源：可連線，但解析 0 筆" in lines
    assert any(line.startswith("故障來源：失敗") for line in lines)
