# -*- coding: utf-8 -*-

from typing import Any

from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.http_client import SafeHttpClient
from src.collectors.moe_overseas_collector import (
    OVERSEAS_CHILD_SOURCES,
    MoeOverseasCollector,
)


# 四個子站都應各自解析公告，再聚合成教育部留學來源。
def test_moe_overseas_collects_four_child_sources(monkeypatch: Any) -> None:
    def fake_get_text(_: SafeHttpClient, url: str) -> str:
        slug = url.rstrip("/").split("/")[-1]
        return f"""
        <section>
          <div class="announcement">
            <h3><a href="{url}/notice/{slug}">{slug} 獎學金甄選簡章</a></h3>
            <p>發佈日期 2026-05-13</p>
          </div>
        </section>
        """

    monkeypatch.setattr(SafeHttpClient, "get_text", fake_get_text)
    collector = MoeOverseasCollector(
        10.0,
        "test",
        CollectionMode.INCREMENTAL,
        10,
    )

    records = collector.collect()

    assert len(records) == 4
    assert {item.source for item in records} == {
        "moe-studyabroad",
        "moe-top100",
        "moe-overseas-scholarship",
        "moe-eu-scholarship",
    }
    assert collector.diagnostic.child_sources_detected == 4
    assert collector.diagnostic.child_sources_succeeded == 4
    assert collector.diagnostic.completeness == "incremental"


# parser 必須排除固定導覽標題，只保留有日期的公告標題。
def test_moe_overseas_parser_filters_navigation_heading() -> None:
    html = """
    <main>
      <h2>各項公告</h2>
      <div class="announcement">
        <h3><a href="/eu/notice/1">115年教育部歐盟獎學金甄選簡章</a></h3>
        <p>發佈日期 2026-05-13</p>
      </div>
    </main>
    """
    collector = MoeOverseasCollector(
        10.0,
        "test",
        CollectionMode.FULL_AUDIT,
        10,
    )
    child = OVERSEAS_CHILD_SOURCES[-1]

    records, candidate_count = collector._parse_page(html, child, child.list_url)

    assert candidate_count == 1
    assert len(records) == 1
    assert records[0].title == "115年教育部歐盟獎學金甄選簡章"
    assert records[0].published_date == "2026-05-13"
