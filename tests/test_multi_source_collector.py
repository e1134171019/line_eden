# -*- coding: utf-8 -*-

from src.collectors.base_collector import BaseCollector
from src.collectors.multi_source_collector import CollectorSource, MultiSourceCollector
from src.models.scholarship import Scholarship


class StubCollector(BaseCollector):
    def __init__(self, records: list[Scholarship] | None = None, error: Exception | None = None) -> None:
        self.records = records or []
        self.error = error

    def collect(self) -> list[Scholarship]:
        if self.error:
            raise self.error
        return self.records


def _item(source: str, title: str, url: str) -> Scholarship:
    return Scholarship.from_raw(source, title, "2026-07-28", url)


# 單一官方來源失敗時，其餘來源仍可完成蒐集。
def test_multi_source_collector_isolates_one_source_failure() -> None:
    collector = MultiSourceCollector([
        CollectorSource("failed", "失敗來源", StubCollector(error=RuntimeError("timeout"))),
        CollectorSource(
            "working",
            "正常來源",
            StubCollector([_item("working", "115年測試獎學金", "https://b.test/1")]),
        ),
    ])

    records = collector.collect()

    assert len(records) == 1
    assert collector.last_diagnostics[0].status == "error"
    assert collector.last_diagnostics[1].status == "success"


# 同名公告由不同官方網站轉載時，只保留優先序較前的一筆。
def test_multi_source_collector_deduplicates_across_sources() -> None:
    first = _item("school", "公告：115年優秀學生獎學金", "https://school.test/1")
    second = _item("government", "【公告】115年優秀學生獎學金", "https://gov.test/1")
    collector = MultiSourceCollector([
        CollectorSource("school", "學校", StubCollector([first])),
        CollectorSource("government", "政府", StubCollector([second])),
    ])

    records = collector.collect()

    assert records == [first]
    assert collector.last_diagnostics[0].collected_count == 1
    assert collector.last_diagnostics[1].collected_count == 0


# 所有來源都失敗時必須 fail closed，不得假裝成功。
def test_multi_source_collector_fails_when_all_sources_fail() -> None:
    collector = MultiSourceCollector([
        CollectorSource("a", "來源 A", StubCollector(error=RuntimeError("A failed"))),
        CollectorSource("b", "來源 B", StubCollector(error=RuntimeError("B failed"))),
    ])

    try:
        collector.collect()
    except RuntimeError as error:
        assert "全部官方來源蒐集失敗" in str(error)
    else:
        raise AssertionError("全部來源失敗時應拋出 RuntimeError")
