# -*- coding: utf-8 -*-

from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import (
    AccountingStatus,
    CollectorDiagnostic,
    SourceAccessMode,
    SourceTargetDiagnostic,
)
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
        self.diagnostic = diagnostic or CollectorDiagnostic(
            completeness="complete",
            pages_detected=1,
            pages_requested=1,
            pages_succeeded=1,
            raw_rows=len(items),
            parsed_rows=len(items),
        )

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
        "頂層來源群組：設定 3，成功產生資料 1，空結果 1，部分完成 0，失敗 1；"
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
        raw_rows=3,
        parsed_rows=1,
        rejected_rows=2,
        stop_reason="all_detected_pages_completed",
    )
    collector = MultiSourceCollector([
        StubCollector("龍華科技大學", [_item()], diagnostic),
    ])

    collector.collect()
    lines = collector.summary_lines()

    assert lines[0].endswith("整體：正常")
    assert lines[2] == (
        "跨來源資料守恆：來源輸出 1 = 保留 1 + 重複關聯 0 + 驗證隔離 0"
    )
    assert lines[3] == (
        "龍華科技大學：完整；頁面 5/5；原始列 3，解析 1，排除 2；"
        "跨來源去重後保留 1/1 筆；停止：all_detected_pages_completed"
    )
    assert collector.diagnostics[0].row_accounting.status is AccountingStatus.BALANCED


# 聚合來源必須區分邏輯目標、直接入口、核心涵蓋與唯一網域。
def test_source_summary_reports_logical_target_scope() -> None:
    targets = (
        SourceTargetDiagnostic(
            "direct-a",
            "直接方案 A",
            SourceAccessMode.DIRECT,
            "https://one.example/news",
            "complete",
            pages_succeeded=1,
            raw_rows=1,
            parsed_rows=1,
        ),
        SourceTargetDiagnostic(
            "direct-b",
            "直接方案 B",
            SourceAccessMode.DIRECT,
            "https://one.example/news",
            "complete",
            pages_succeeded=1,
            raw_rows=1,
            parsed_rows=1,
        ),
        SourceTargetDiagnostic(
            "covered",
            "核心涵蓋方案",
            SourceAccessMode.CORE_COVERED,
            completeness="covered",
            raw_rows=1,
            parsed_rows=1,
        ),
    )
    diagnostic = CollectorDiagnostic(
        completeness="complete",
        raw_rows=1,
        parsed_rows=1,
        child_sources_detected=3,
        child_sources_succeeded=3,
        target_diagnostics=targets,
    )
    collector = MultiSourceCollector([
        StubCollector("聚合來源", [_item()], diagnostic),
    ])

    collector.collect()
    lines = collector.summary_lines()

    assert lines[1] == (
        "監測目標：邏輯 3，直接 2，核心涵蓋 1，待確認 0；"
        "唯一入口 URL 1，唯一網域 1"
    )
    assert any(
        "監測目標 3/3（直接 2、核心涵蓋 1、入口 1、網域 1）" in line
        for line in lines
    )


# 聚合來源的部分完成子目標必須展開錯誤，不得只顯示總數。
def test_source_summary_expands_child_target_anomaly() -> None:
    target = SourceTargetDiagnostic(
        "partial",
        "測試方案",
        SourceAccessMode.DIRECT,
        "https://partial.example/news",
        "partial",
        pages_detected=3,
        pages_requested=3,
        pages_succeeded=2,
        error="第三頁逾時",
    )
    diagnostic = CollectorDiagnostic(
        completeness="partial",
        raw_rows=1,
        parsed_rows=1,
        child_sources_detected=1,
        child_sources_succeeded=1,
        target_diagnostics=(target,),
        stop_reason="program_watch_incremental_catchup_pages",
    )
    collector = MultiSourceCollector([
        StubCollector("聚合來源", [_item()], diagnostic),
    ])

    collector.collect()
    lines = collector.summary_lines()

    assert lines[-1] == "聚合來源／測試方案：partial；頁面 2/3；錯誤：第三頁逾時"
