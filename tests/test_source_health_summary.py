# -*- coding: utf-8 -*-

from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectorDiagnostic
from src.collectors.multi_source_collector import MultiSourceCollector
from src.models.scholarship import Scholarship


class StubCollector(BaseCollector):
    def __init__(
        self,
        source_label: str,
        items: list[Scholarship],
        diagnostic: CollectorDiagnostic | None = None,
    ) -> None:
        self.source_label = source_label
        self.items = items
        self.diagnostic = diagnostic or CollectorDiagnostic()

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

    assert lines[0] == (
        "來源網站：設定 3，成功產生資料 1，空結果 1，部分完成 0，失敗 1；"
        "整體：降級"
    )
    assert "空來源：可連線，但解析 0 筆" in lines
    assert any(line.startswith("故障來源：失敗") for line in lines)


# 完整稽核摘要必須分開顯示頁面、原始列與公告保留數。
def test_source_summary_reports_page_completeness() -> None:
    diagnostic = CollectorDiagnostic(
        completeness="complete",
        pages_detected=5,
        pages_requested=5,
        pages_succeeded=5,
        raw_rows=500,
        parsed_rows=498,
        rejected_rows=2,
        stop_reason="all_detected_pages_completed",
    )
    collector = MultiSourceCollector([
        StubCollector("龍華科技大學", [_item()], diagnostic),
    ])

    collector.collect()
    lines = collector.summary_lines()

    assert lines[0].endswith("整體：正常")
    assert lines[1] == (
        "龍華科技大學：完整；頁面 5/5；原始列 500，解析 498，排除 2；"
        "跨來源去重後保留 1/1 筆；停止：all_detected_pages_completed"
    )
