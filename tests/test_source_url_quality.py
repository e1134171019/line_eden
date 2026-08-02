# -*- coding: utf-8 -*-

from src.catalogs.tun_program_sources import ResolvedProgramSource, resolved_programs
from src.collectors.expanded_scholarship_collector import _tun_quality_summary
from src.collectors.tun_program_watch_collector import (
    ProgramSourceState,
    TunProgramWatchCollector,
    _extract_program_notices,
)
from src.models.source_quality import SourceRisk, SourceUrlType


# 常設方案頁即使沒有日期與獨立 detail link，也可把自身作為候選。
def test_evergreen_page_can_be_direct_candidate() -> None:
    program = ResolvedProgramSource(
        "evergreen",
        "固定助學金",
        "測試基金會",
        ("固定助學金",),
        "https://foundation.example/project",
        "verified",
        "example-foundation",
        SourceUrlType.EVERGREEN,
        ("foundation.example",),
        "固定頁更新年度辦法。",
        SourceRisk.LOW,
        tuple(),
        "2026-08-02",
    )
    html = """
    <main>
      <h1>固定助學金</h1>
      <p>申請資格：國內大專院校在校生可申請。</p>
    </main>
    """

    records, matched = _extract_program_notices(
        html,
        program.official_url,
        (program,),
    )

    assert matched >= 1
    assert len(records) == 1
    assert records[0].source_url == program.official_url
    assert records[0].published_date == ""


# 列表頁沒有日期且沒有獨立連結時，不得把入口偽造成當期公告。
def test_list_page_still_requires_detail_link_or_date() -> None:
    program = ResolvedProgramSource(
        "list",
        "列表助學金",
        "測試基金會",
        ("列表助學金",),
        "https://foundation.example/news",
        "verified",
        "example-foundation",
        SourceUrlType.LIST,
        ("foundation.example",),
        "列表發現年度公告。",
        SourceRisk.LOW,
        tuple(),
        "2026-08-02",
    )

    records, matched = _extract_program_notices(
        "<main><h1>列表助學金</h1></main>",
        program.official_url,
        (program,),
    )

    assert matched == 1
    assert records == []


# 狀態輸出必須同時顯示 URL 品質與跨年度風險。
def test_program_status_lines_include_url_type_and_risk() -> None:
    collector = TunProgramWatchCollector(1.0, "test-agent")
    collector.program_states = (
        ProgramSourceState(
            "test",
            "測試獎學金",
            "https://foundation.example/news",
            "no_candidate",
            0,
            "入口正常但尚無公告。",
            SourceUrlType.LIST,
            SourceRisk.LOW,
        ),
    )

    line = collector.program_status_lines()[0]

    assert "URL類型 url_list" in line
    assert "風險 low" in line


# 來源摘要必須分開顯示 URL 類型分布與高風險數量。
def test_url_quality_summary_counts_types_and_high_risk() -> None:
    states = (
        ProgramSourceState(
            "list",
            "列表方案",
            "https://example.test/news",
            "configured",
            source_url_type=SourceUrlType.LIST,
            update_risk=SourceRisk.LOW,
        ),
        ProgramSourceState(
            "relay",
            "轉載方案",
            "https://example.test/detail",
            "configured",
            source_url_type=SourceUrlType.RELAY_DETAIL,
            update_risk=SourceRisk.HIGH,
        ),
    )

    line = _tun_quality_summary(states)

    assert "url_list 1" in line
    assert "url_relay_detail 1" in line
    assert "高風險 1" in line


# 38 項品質契約不得把申請系統或錯頁當作主要監測入口。
def test_resolved_programs_do_not_use_blocked_primary_types() -> None:
    blocked = {
        SourceUrlType.APPLICATION_PORTAL,
        SourceUrlType.PENDING,
        SourceUrlType.WRONG,
    }

    assert all(item.source_url_type not in blocked for item in resolved_programs())
