# -*- coding: utf-8 -*-

from src.collectors.base_collector import BaseCollector
from src.collectors.multi_source_collector import MultiSourceCollector
from src.models.scholarship import Scholarship


class StubCollector(BaseCollector):
    def __init__(self, items: list[Scholarship]) -> None:
        self.items = items

    def collect(self) -> list[Scholarship]:
        return self.items


class BrokenCollector(BaseCollector):
    def collect(self) -> list[Scholarship]:
        raise RuntimeError("source unavailable")


def _item(source: str, title: str, day: str, url: str) -> Scholarship:
    return Scholarship.from_raw(source, title, day, url)


def test_multi_source_deduplicates_same_title_and_date() -> None:
    first = _item("a", "測試獎學金", "2026-07-01", "https://a.example/1")
    duplicate = _item("b", "測試 獎學金", "2026-07-01", "https://b.example/2")
    collector = MultiSourceCollector([StubCollector([first]), StubCollector([duplicate])])

    records = collector.collect()

    assert records == [first]


def test_multi_source_keeps_other_sources_when_one_fails() -> None:
    item = _item("ok", "可用助學金", "2026-07-02", "https://ok.example/1")
    collector = MultiSourceCollector([BrokenCollector(), StubCollector([item])])

    records = collector.collect()

    assert records == [item]
    assert len(collector.failures) == 1
    assert collector.failures[0].source == "BrokenCollector"
