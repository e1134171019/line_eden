# -*- coding: utf-8 -*-

import pytest

from src.catalogs.additional_source_catalog import (
    ADDITIONAL_SCHOLARSHIP_SOURCES,
    AdditionalScholarshipSource,
)
from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
    _extract_date,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.listing_paginator import ListingCrawlResult, ListingPage


def _config(**overrides: object) -> AdditionalScholarshipSource:
    values: dict[str, object] = {
        "source_id": "test-source",
        "display_name": "測試獎學金來源",
        "entry_url": "https://scholar.example/list",
        "allowed_hosts": ("scholar.example",),
        "review_reason": "測試來源已完成有效性審查。",
        "max_pages": 3,
    }
    values.update(overrides)
    return AdditionalScholarshipSource(**values)  # type: ignore[arg-type]


def _collector(
    config: AdditionalScholarshipSource | None = None,
) -> AdditionalScholarshipSourceCollector:
    return AdditionalScholarshipSourceCollector(
        config or _config(),
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        200,
    )


def test_additional_source_parser_keeps_only_allowed_scholarship_links() -> None:
    collector = _collector()
    html = """
    <ul>
      <li><span>2026/07/01</span>
        <a href="/detail/1">【轉知】台灣電力與能源工程協會獎學金</a>
      </li>
      <li><a href="/activity">一般活動公告</a></li>
      <li><a href="/scholarships">校外獎助學金</a></li>
      <li><a href="https://outside.example/scholarship">外站獎學金</a></li>
      <li><a href="javascript:void(0)">測試獎學金</a></li>
    </ul>
    """

    records, raw_rows = collector._parse_html(html, collector.config.entry_url)

    assert raw_rows == 5
    assert len(records) == 1
    assert records[0].title == "【轉知】台灣電力與能源工程協會獎學金"
    assert records[0].published_date == "2026-07-01"
    assert records[0].detail_url == "https://scholar.example/detail/1"
    assert records[0].entry_url == collector.config.entry_url


def test_additional_source_parser_reads_roc_and_url_dates() -> None:
    collector = _collector()
    html = """
    <article><time>115-08-05</time><a href="/post/a">甲獎助學金</a></article>
    <article><a href="/2026/09/10/post-b/">乙助學金</a></article>
    """

    records, _ = collector._parse_html(html, collector.config.entry_url)

    assert [item.published_date for item in records] == ["2026-08-05", "2026-09-10"]
    assert _extract_date("2026-13-40", "https://scholar.example/no-date") == ""


def test_additional_source_collect_adds_entry_record_and_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.collectors.additional_scholarship_source_collector as module

    config = _config(entry_title="固定官方科技獎學金")
    collector = _collector(config)
    html = '<a href="/detail/1">115年度測試獎學金</a>'

    class FakeClient:
        fallback_hosts: set[str] = set()

        def __init__(self, *_: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get_text(self, _: str) -> str:
            return html

    def fake_crawl(*_: object, **__: object) -> ListingCrawlResult:
        return ListingCrawlResult(
            pages=(ListingPage(config.entry_url, html),),
            pages_detected=1,
            pages_requested=1,
            pages_succeeded=1,
            completeness="incremental",
            stop_reason="incremental_first_page",
            errors=tuple(),
        )

    monkeypatch.setattr(module, "SafeHttpClient", FakeClient)
    monkeypatch.setattr(module, "crawl_listing_pages", fake_crawl)

    records = collector.collect()

    assert [item.title for item in records] == [
        "固定官方科技獎學金",
        "115年度測試獎學金",
    ]
    assert collector.source_label == "測試獎學金來源"
    assert collector.max_pages == 3
    assert collector.diagnostic.pages_succeeded == 1
    assert collector.diagnostic.parsed_rows == 2
    assert collector.diagnostic.stop_reason == "incremental_first_page"


def test_additional_source_collect_raises_when_fetch_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.collectors.additional_scholarship_source_collector as module

    collector = _collector()

    class FakeClient:
        fallback_hosts = {"scholar.example"}

        def __init__(self, *_: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get_text(self, _: str) -> str:
            return ""

    def fake_crawl(*_: object, **__: object) -> ListingCrawlResult:
        return ListingCrawlResult(
            pages=tuple(),
            pages_detected=1,
            pages_requested=1,
            pages_succeeded=0,
            completeness="failed",
            stop_reason="entry_fetch_failed",
            errors=("https://scholar.example/list（timeout）",),
        )

    monkeypatch.setattr(module, "SafeHttpClient", FakeClient)
    monkeypatch.setattr(module, "crawl_listing_pages", fake_crawl)

    with pytest.raises(RuntimeError, match="timeout"):
        collector.collect()

    assert collector.diagnostic.ssl_compatibility_fallback is True
    assert collector.diagnostic.completeness == "failed"


def test_additional_source_catalog_has_twelve_reviewed_unique_sources() -> None:
    assert len(ADDITIONAL_SCHOLARSHIP_SOURCES) == 12
    assert len({item.source_id for item in ADDITIONAL_SCHOLARSHIP_SOURCES}) == 12
    assert all(item.entry_url.startswith("https://") for item in ADDITIONAL_SCHOLARSHIP_SOURCES)
    assert all(item.review_reason.strip() for item in ADDITIONAL_SCHOLARSHIP_SOURCES)
    assert {
        "pan-wen-yuan-scholarship",
        "ntut-scholarship-platform",
        "utaipei-external-scholarships",
        "uch-external-scholarships",
        "npu-scholarship-portal",
        "tut-external-scholarships",
    }.issubset({item.source_id for item in ADDITIONAL_SCHOLARSHIP_SOURCES})
    assert "foxconn-scholarship-whale" not in {
        item.source_id for item in ADDITIONAL_SCHOLARSHIP_SOURCES
    }
