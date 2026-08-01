# -*- coding: utf-8 -*-

import pytest

from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import (
    CollectorDiagnostic,
    RejectionReasonCount,
    SourceAccessMode,
    SourceTargetDiagnostic,
)
from src.collectors.multi_source_collector import MultiSourceCollector
from src.models.scholarship import Scholarship


class StubCollector(BaseCollector):
    def __init__(self, items: list[Scholarship], source_label: str = "測試來源") -> None:
        self.items = items
        self.source_label = source_label
        self.diagnostic = CollectorDiagnostic(
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
    source_label = "故障官方來源"

    def collect(self) -> list[Scholarship]:
        raise RuntimeError("source unavailable")


class TargetAwareStubCollector(StubCollector):
    """測試聚合來源可把每筆公告映射回自己的子目標。"""

    def target_id_for(self, notice: Scholarship) -> str:
        return notice.source.removeprefix("tun-program-")


def _item(source: str, title: str, day: str, url: str) -> Scholarship:
    return Scholarship.from_raw(source, title, day, url)


# 轉知前綴與不同刊登日期不應造成同一獎學金重複。
def test_multi_source_deduplicates_wrapped_title_across_dates() -> None:
    first = _item("a", "115年度測試獎學金", "2026-07-01", "https://a.example/1")
    duplicate = _item(
        "b",
        "【轉知】115年度測試 獎學金",
        "2026-07-03",
        "https://b.example/2",
    )
    collector = MultiSourceCollector([
        StubCollector([first], "來源 A"),
        StubCollector([duplicate], "來源 B"),
    ])

    records = collector.collect()

    assert records == [first]
    assert collector.source_records == (first, duplicate)
    assert len(collector.duplicate_records) == 1
    assert collector.duplicate_records[0].canonical == first
    assert collector.duplicate_records[0].duplicate == duplicate
    assert collector.diagnostics[1].duplicate_count == 1


# 同一公告出現在三個來源時，只保留一筆公告並留下兩筆來源關聯。
def test_multi_source_preserves_three_source_duplicate_relations() -> None:
    first = _item("a", "115年度測試獎學金", "2026-07-01", "https://a.example/1")
    second = _item("b", "轉知：115年度測試獎學金", "2026-07-02", "https://b.example/2")
    third = _item("c", "【公告】115年度測試獎學金", "2026-07-03", "https://c.example/3")
    collector = MultiSourceCollector([
        StubCollector([first], "來源 A"),
        StubCollector([second], "來源 B"),
        StubCollector([third], "來源 C"),
    ])

    assert collector.collect() == [first]
    assert len(collector.duplicate_records) == 2
    assert {relation.duplicate.source for relation in collector.duplicate_records} == {"b", "c"}


# 過短的泛稱公告要保留日期，避免不同梯次被錯誤合併。
def test_multi_source_keeps_short_generic_titles_on_different_dates() -> None:
    first = _item("a", "獎學金公告", "2026-07-01", "https://a.example/1")
    second = _item("b", "獎學金公告", "2026-07-03", "https://b.example/2")
    collector = MultiSourceCollector([StubCollector([first]), StubCollector([second])])

    assert collector.collect() == [first, second]


# 同一方案跨年度必須保留兩個申請週期，不得以標題直接折疊。
def test_multi_source_keeps_same_named_notice_across_years() -> None:
    older = _item("a", "測試獎學金", "2025-09-01", "https://a.example/2025")
    current = _item("b", "測試獎學金", "2026-09-01", "https://b.example/2026")
    collector = MultiSourceCollector([
        StubCollector([older], "來源 A"),
        StubCollector([current], "來源 B"),
    ])

    assert collector.collect() == [older, current]
    assert collector.duplicate_records == tuple()


# 單站失敗要保留其他來源，並提供可辨識的官方來源名稱。
def test_multi_source_keeps_other_sources_when_one_fails() -> None:
    item = _item("ok", "可用助學金", "2026-07-02", "https://ok.example/1")
    collector = MultiSourceCollector([
        BrokenCollector(),
        StubCollector([item], "正常官方來源"),
    ])

    records = collector.collect()
    lines = collector.summary_lines()

    assert records == [item]
    assert len(collector.failures) == 1
    assert collector.failures[0].source == "故障官方來源"
    assert lines[0].startswith("頂層來源群組：設定 2，成功產生資料 1")
    assert any(
        line.startswith("正常官方來源：完整；頁面 1/1；原始列 1，解析 1，排除 0")
        for line in lines
    )


# 五個來源全部故障時不得回傳空清單假裝成功。
def test_multi_source_fails_closed_when_all_sources_fail() -> None:
    collector = MultiSourceCollector([BrokenCollector(), BrokenCollector()])

    with pytest.raises(RuntimeError, match="官方來源全部失敗"):
        collector.collect()


# 來源可連線但全部解析為空時，視為版型異常而非正常無公告。
def test_multi_source_fails_when_all_successful_sources_are_empty() -> None:
    collector = MultiSourceCollector([
        StubCollector([], "空來源 A"),
        StubCollector([], "空來源 B"),
    ])

    with pytest.raises(RuntimeError, match="沒有解析到任何獎助學金公告"):
        collector.collect()


# 未通過列數契約的來源必須先隔離，不能進入跨來源去重。
def test_multi_source_quarantines_unvalidated_source_before_deduplication() -> None:
    invalid = _item("bad", "資料異常獎學金", "2026-07-01", "https://bad.example/1")
    valid = _item("ok", "有效助學金", "2026-07-02", "https://ok.example/1")
    invalid_collector = StubCollector([invalid], "異常來源")
    invalid_collector.diagnostic = CollectorDiagnostic(
        completeness="complete",
        pages_detected=1,
        pages_requested=1,
        pages_succeeded=1,
        raw_rows=2,
        parsed_rows=2,
    )
    collector = MultiSourceCollector([
        invalid_collector,
        StubCollector([valid], "正常來源"),
    ])

    records = collector.collect()

    assert records == [valid]
    assert collector.source_records == (invalid, valid)
    assert collector.quarantined_records == (invalid,)
    assert collector.duplicate_records == ()
    assert collector.diagnostics[0].status == "error"
    assert "列數不守恆" in collector.diagnostics[0].error


# 同一 Collector 產出重複 identity 時必須隔離，不能等 Repository 才折疊。
def test_multi_source_quarantines_duplicate_identity_before_deduplication() -> None:
    duplicate = _item("bad", "重複獎學金", "2026-07-01", "https://bad.example/1")
    valid = _item("ok", "有效助學金", "2026-07-02", "https://ok.example/1")
    collector = MultiSourceCollector([
        StubCollector([duplicate, duplicate], "重複來源"),
        StubCollector([valid], "正常來源"),
    ])

    records = collector.collect()
    lines = collector.summary_lines()

    assert records == [valid]
    assert collector.quarantined_records == (duplicate, duplicate)
    assert any("驗證失敗，隔離 2 筆" in line for line in lines)
    assert "重複 identity" in collector.diagnostics[0].error
    assert "https://bad.example/1" in collector.diagnostics[0].error
    assert "2026-07-01:重複獎學金" in collector.diagnostics[0].error


# 完整稽核若只有 HTTP 成功但方案未命中，必須在跨來源去重前隔離。
def test_full_audit_quarantines_semantically_unverified_targets() -> None:
    unverified = _item(
        "tun-program-missing",
        "其他獎學金",
        "2026-07-01",
        "https://foundation.example/other",
    )
    target = SourceTargetDiagnostic(
        "missing",
        "應監測方案",
        SourceAccessMode.DIRECT,
        "https://foundation.example/news",
        "partial",
        pages_detected=1,
        pages_requested=1,
        pages_succeeded=1,
        raw_rows=0,
        parsed_rows=0,
        error="入口可連線但未命中方案別名",
    )
    tun_collector = StubCollector([unverified], "方案監測")
    tun_collector.diagnostic = CollectorDiagnostic(
        completeness="partial",
        pages_detected=1,
        pages_requested=1,
        pages_succeeded=1,
        raw_rows=1,
        parsed_rows=1,
        stop_reason="program_watch_partial",
        child_sources_detected=1,
        child_sources_succeeded=0,
        target_diagnostics=(target,),
    )
    valid = _item("core", "有效助學金", "2026-07-02", "https://core.example/1")
    collector = MultiSourceCollector([tun_collector, StubCollector([valid], "核心來源")])

    assert collector.collect() == [valid]
    assert collector.quarantined_records == (unverified,)
    assert "未通過語意驗證" in collector.diagnostics[0].error


# 聚合來源中一個方案失敗時，只能隔離該方案，不得連坐成功方案。
def test_target_aware_source_keeps_valid_program_when_sibling_fails() -> None:
    valid = _item(
        "tun-program-auden-university-talent",
        "2026耀登炳南大專院校優秀人才獎學金",
        "2026-07-23",
        "https://www.auden.com.tw/2026scholarship/",
    )
    invalid = _item(
        "tun-program-missing",
        "錯誤入口產生的公告",
        "2026-07-20",
        "https://missing.example/notice",
    )
    collector = TargetAwareStubCollector([valid, invalid], "TUN 方案監測")
    collector.diagnostic = CollectorDiagnostic(
        completeness="partial",
        pages_detected=2,
        pages_requested=2,
        pages_succeeded=2,
        raw_rows=2,
        parsed_rows=2,
        stop_reason="program_watch_partial",
        child_sources_detected=2,
        child_sources_succeeded=1,
        target_diagnostics=(
            SourceTargetDiagnostic(
                "auden-university-talent",
                "耀登炳南大專院校優秀人才獎學金",
                SourceAccessMode.DIRECT,
                valid.source_url,
                "complete",
                pages_detected=1,
                pages_requested=1,
                pages_succeeded=1,
                raw_rows=1,
                parsed_rows=1,
            ),
            SourceTargetDiagnostic(
                "missing",
                "錯誤方案",
                SourceAccessMode.DIRECT,
                "https://missing.example",
                "partial",
                pages_detected=1,
                pages_requested=1,
                pages_succeeded=1,
                error="入口可連線但未命中方案別名",
            ),
        ),
    )
    multi_source = MultiSourceCollector([collector])

    assert multi_source.collect() == [valid]
    assert multi_source.quarantined_records == (invalid,)
    assert multi_source.diagnostics[0].status == "partial"
    assert multi_source.diagnostics[0].accepted_count == 1
    assert multi_source.diagnostics[0].validation is not None
    assert multi_source.diagnostics[0].validation.errors == tuple()


# 解析 100 列、排除 20 列時，排除原因數量必須完整守恆。
def test_rejection_reason_accounting_explains_every_excluded_row() -> None:
    notices = [
        _item(
            "audit",
            f"第 {index} 筆獎學金",
            "2026-07-01",
            f"https://audit.example/{index}",
        )
        for index in range(80)
    ]
    audited = StubCollector(notices, "守恆來源")
    audited.diagnostic = CollectorDiagnostic(
        completeness="complete",
        pages_detected=1,
        pages_requested=1,
        pages_succeeded=1,
        raw_rows=100,
        parsed_rows=80,
        rejected_rows=20,
        rejection_reasons=(
            RejectionReasonCount("非申請公告", 12),
            RejectionReasonCount("缺少必要欄位", 8),
        ),
    )
    collector = MultiSourceCollector([audited])

    assert len(collector.collect()) == 80
    assert collector.diagnostics[0].validation is not None
    assert collector.diagnostics[0].validation.errors == tuple()
