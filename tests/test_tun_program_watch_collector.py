# -*- coding: utf-8 -*-

from typing import cast

import httpx
from pytest import MonkeyPatch

from src.catalogs.tun_2025_program_catalog import ScholarshipProgramWatch
from src.collectors.http_client import DetailSafeHttpClient
from src.collectors.tun_program_watch_collector import (
    _extract_program_notices,
    _fetch_text_with_retry,
    _group_programs_by_url,
)


def _program(
    program_id: str,
    title: str,
    url: str = "https://foundation.example/news",
) -> ScholarshipProgramWatch:
    return ScholarshipProgramWatch(
        program_id,
        title,
        "測試基金會",
        (title,),
        url,
        "verified",
    )


class _TimeoutThenSuccessClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_text(self, _: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise httpx.ReadTimeout("temporary timeout")
        return "<html>ok</html>"


# 同一主辦單位的方案必須合併為一次官方頁面請求。
def test_groups_programs_by_shared_official_url() -> None:
    programs = (
        _program("one", "第一獎學金"),
        _program("two", "第二獎學金"),
        _program("three", "第三獎學金", "https://other.example/news"),
    )

    grouped = _group_programs_by_url(programs)

    assert len(grouped) == 2
    assert [item.program_id for item in grouped["https://foundation.example/news"]] == [
        "one",
        "two",
    ]


# 暫時性 timeout 只重試一次，成功後不得繼續請求。
def test_fetch_retries_one_transient_timeout(monkeypatch: MonkeyPatch) -> None:
    client = _TimeoutThenSuccessClient()
    monkeypatch.setattr(
        "src.collectors.tun_program_watch_collector.time.sleep",
        lambda _: None,
    )

    result = _fetch_text_with_retry(
        cast(DetailSafeHttpClient, client),
        "https://foundation.example/news",
    )

    assert result == "<html>ok</html>"
    assert client.calls == 2


# 官方公告列的西元日期應轉成 Scholarship 標準日期。
def test_extracts_gregorian_dated_program_notice() -> None:
    program = _program("energy", "能源工程獎學金")
    html = """
    <ul>
      <li><span>2026/09/15</span><a href="/news/88">能源工程獎學金開放申請</a></li>
    </ul>
    """

    records, matched = _extract_program_notices(
        html,
        "https://foundation.example/news",
        (program,),
    )

    assert matched >= 1
    assert len(records) == 1
    assert records[0].published_date == "2026-09-15"
    assert records[0].source_url == "https://foundation.example/news/88"


# 民國日期應轉成西元，確保後續期限推定具有正確年度。
def test_extracts_roc_dated_program_notice() -> None:
    program = _program("electronics", "電子人才獎學金")
    html = """
    <article>
      <h2><a href="notice-115">電子人才獎學金申請公告</a></h2>
      <time datetime="115年8月3日">115年8月3日</time>
    </article>
    """

    records, _ = _extract_program_notices(
        html,
        "https://foundation.example/news/",
        (program,),
    )

    assert len(records) == 1
    assert records[0].published_date == "2026-08-03"


# 靜態介紹頁即使出現方案名稱，沒有可靠日期也不得偽造當期公告。
def test_skips_static_program_page_without_date() -> None:
    program = _program("static", "長期助學金")
    html = "<main><h1>長期助學金</h1><p>本會長期推動學生扶助。</p></main>"

    records, matched = _extract_program_notices(
        html,
        "https://foundation.example/project",
        (program,),
    )

    assert matched == 1
    assert records == []
