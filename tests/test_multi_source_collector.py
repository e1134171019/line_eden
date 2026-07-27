# -*- coding: utf-8 -*-

import pytest

from src.collectors.base_collector import BaseCollector
from src.collectors.multi_source_collector import MultiSourceCollector
from src.models.scholarship import Scholarship


class StubCollector(BaseCollector):
    def __init__(self, items: list[Scholarship], source_label: str = "測試來源") -> None:
        self.items = items
        self.source_label = source_label

    def collect(self) -> list[Scholarship]:
        return self.items


class BrokenCollector(BaseCollector):
    source_label = "故障官方來源"

    def collect(self) -> list[Scholarship]:
        raise RuntimeError("source unavailable")


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
    assert collector.diagnostics[1].duplicate_count == 1


# 過短的泛稱公告要保留日期，避免不同梯次被錯誤合併。
def test_multi_source_keeps_short_generic_titles_on_different_dates() -> None:
    first = _item("a", "獎學金公告", "2026-07-01", "https://a.example/1")
    second = _item("b", "獎學金公告", "2026-07-03", "https://b.example/2")
    collector = MultiSourceCollector([StubCollector([first]), StubCollector([second])])

    assert collector.collect() == [first, second]


# 單站失敗要保留其他來源，並提供可辨識的官方來源名稱。
def test_multi_source_keeps_other_sources_when_one_fails() -> None:
    item = _item("ok", "可用助學金", "2026-07-02", "https://ok.example/1")
    collector = MultiSourceCollector([
        BrokenCollector(),
        StubCollector([item], "正常官方來源"),
    ])

    records = collector.collect()

    assert records == [item]
    assert len(collector.failures) == 1
    assert collector.failures[0].source == "故障官方來源"
    assert "正常官方來源：讀取 1 筆，保留 1 筆" in collector.summary_lines()


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
