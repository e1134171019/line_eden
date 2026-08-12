# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    AdditionalScholarshipSource,
    AdditionalSourceAdapterId,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.npu_latestevent_scholarship_collector import (
    NpuLatestEventScholarshipCollector,
)


def _collector() -> NpuLatestEventScholarshipCollector:
    config = AdditionalScholarshipSource(
        source_id="npu-latestevent-test",
        display_name="NPU LatestEvent 測試來源",
        entry_url=(
            "https://www.npu.edu.tw/sub/latestevent/index.aspx?"
            "Parser=9%2C22%2C501%2C486"
        ),
        allowed_hosts=("npu.edu.tw", "www.npu.edu.tw"),
        review_reason="測試 NPU LatestEvent URL contract。",
        adapter_id=AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST,
        max_pages=10,
    )
    return NpuLatestEventScholarshipCollector(
        config,
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        10,
    )


def test_npu_keeps_only_same_host_latestevent_detail_links() -> None:
    collector = _collector()
    html = """
    <table>
      <tr>
        <td>2026-08-10</td>
        <td><a href="/sub/latestevent/Details.aspx?Parser=9%2C22%2C501%2C486%2C1234">
          115年度測試學生獎
        </a></td>
      </tr>
      <tr><td><a href="/sub/latestevent/index.aspx?Parser=9">列表</a></td></tr>
      <tr><td><a href="/sub/latestevent/Details.aspx?id=88">缺 Parser</a></td></tr>
      <tr><td><a href="https://outside.example/sub/latestevent/Details.aspx?Parser=1">外站</a></td></tr>
    </table>
    """

    records, raw_rows = collector._parse_html(html, collector.config.entry_url)

    assert raw_rows == 1
    assert [item.title for item in records] == ["115年度測試學生獎"]
    assert records[0].published_date == "2026-08-10"
    assert records[0].detail_url.endswith("Parser=9%2C22%2C501%2C486%2C1234")


def test_npu_parser_query_key_is_case_insensitive() -> None:
    collector = _collector()
    records, raw_rows = collector._parse_html(
        '<a href="/SUB/LATESTEVENT/DETAILS.ASPX?parser=abc">企業人才獎勵方案</a>',
        collector.config.entry_url,
    )

    assert raw_rows == 1
    assert [item.title for item in records] == ["企業人才獎勵方案"]


def test_npu_does_not_treat_title_deadline_as_published_date() -> None:
    collector = _collector()
    records, raw_rows = collector._parse_html(
        '<div><a href="/sub/latestevent/Details.aspx?Parser=abc">某基金會獎學金 115年9月30日截止</a></div>',
        collector.config.entry_url,
    )

    assert raw_rows == 1
    assert len(records) == 1
    assert records[0].published_date == ""
