# -*- coding: utf-8 -*-

import pytest

from src.collectors.collection_diagnostics import CollectionMode, CollectorDiagnostic
from src.collectors.resilient_tun_program_watch_collector import (
    ResilientTunProgramWatchCollector,
)
from src.collectors.tun_program_watch_collector import ProgramSourceState
from src.collectors.validated_tun_program_watch_collector import (
    ValidatedTunProgramWatchCollector,
    _is_upward_navigation_candidate,
    _normalized_path,
)
from src.models.scholarship import Scholarship
from src.models.source_quality import SourceRisk, SourceUrlType


def _scholarship(
    *,
    program_id: str = "songliang-aid",
    title: str = "申請助學金",
    entry_url: str = "https://www.slceas.org.tw/index.php/scholarship/scholarship01",
    detail_url: str = "https://www.slceas.org.tw/index.php/scholarship",
) -> Scholarship:
    return Scholarship.from_raw(
        source=f"tun-program-{program_id}",
        title=title,
        published_date="",
        source_url=detail_url,
        program_id=program_id,
        entry_url=entry_url,
        detail_url=detail_url,
    )


def _state(candidate_count: int = 3) -> ProgramSourceState:
    return ProgramSourceState(
        program_id="songliang-aid",
        title="台灣松樑教育公益促進協會助學金",
        official_url="https://www.slceas.org.tw/index.php/scholarship",
        status="matched",
        candidate_count=candidate_count,
        source_url_type=SourceUrlType.EVERGREEN,
        update_risk=SourceRisk.MEDIUM,
        top_score=115,
        match_method="exact_alias",
    )


def _diagnostic() -> CollectorDiagnostic:
    return CollectorDiagnostic(
        completeness="complete",
        pages_detected=1,
        pages_requested=1,
        pages_succeeded=1,
        raw_rows=3,
        parsed_rows=3,
        rejected_rows=0,
        stop_reason="program_watch_live_contract_passed",
        child_sources_detected=1,
        child_sources_succeeded=1,
    )


# 同 host 且候選是 entry 的父路徑時，是返回導覽，不是公告。
def test_upward_navigation_candidate_is_removed() -> None:
    assert _is_upward_navigation_candidate(_scholarship()) is True


# entry 自身、同頁 PDF、外站轉載與非 force-replace 方案都不得誤刪。
def test_valid_detail_candidates_are_kept() -> None:
    self_page = _scholarship(
        title="助學金實施辦法",
        detail_url="https://www.slceas.org.tw/index.php/scholarship/scholarship01",
    )
    pdf = _scholarship(
        title="助學金實施辦法 PDF",
        detail_url="https://www.slceas.org.tw/upload/scholarship-rules.pdf",
    )
    relay = _scholarship(
        title="正式學校轉載",
        detail_url="https://example.edu.tw/p/404-1000-1.php",
    )
    ordinary_program = _scholarship(
        program_id="auden-university-talent",
        entry_url="https://www.auden.com.tw/2026scholarship/detail",
        detail_url="https://www.auden.com.tw/2026scholarship",
    )

    assert _is_upward_navigation_candidate(self_page) is False
    assert _is_upward_navigation_candidate(pdf) is False
    assert _is_upward_navigation_candidate(relay) is False
    assert _is_upward_navigation_candidate(ordinary_program) is False


# 路徑正規化不能因尾斜線影響父子關係判斷。
def test_normalized_path_removes_trailing_slash() -> None:
    assert _normalized_path("/index.php/scholarship/") == "/index.php/scholarship"
    assert _normalized_path("") == "/"


# 正式 collector 必須移除父層導覽，並依保留候選重算數量。
def test_collect_filters_upward_navigation_and_recounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _scholarship()
    self_page = _scholarship(
        title="助學金實施辦法",
        detail_url="https://www.slceas.org.tw/index.php/scholarship/scholarship01",
    )
    pdf = _scholarship(
        title="助學金實施辦法 PDF",
        detail_url="https://www.slceas.org.tw/upload/scholarship-rules.pdf",
    )

    def fake_collect(instance: ResilientTunProgramWatchCollector) -> list[Scholarship]:
        instance.program_states = (_state(3),)
        instance.diagnostic = _diagnostic()
        return [parent, self_page, pdf]

    monkeypatch.setattr(ResilientTunProgramWatchCollector, "collect", fake_collect)
    collector = ValidatedTunProgramWatchCollector(
        1,
        "test-agent",
        CollectionMode.INCREMENTAL,
        1,
        1,
    )

    result = collector.collect()

    assert parent not in result
    assert self_page in result
    assert pdf in result
    assert collector.program_states[0].status == "matched"
    assert collector.program_states[0].candidate_count == 2
    assert collector.diagnostic.child_sources_succeeded == 1


# 若 force-replace 來源只產生父層導覽，必須回報 matcher_miss 阻擋合併。
def test_collect_marks_failure_when_only_navigation_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _scholarship()

    def fake_collect(instance: ResilientTunProgramWatchCollector) -> list[Scholarship]:
        instance.program_states = (_state(1),)
        instance.diagnostic = _diagnostic()
        return [parent]

    monkeypatch.setattr(ResilientTunProgramWatchCollector, "collect", fake_collect)
    collector = ValidatedTunProgramWatchCollector(1, "test-agent")

    result = collector.collect()

    assert result == []
    assert collector.program_states[0].status == "matcher_miss"
    assert collector.program_states[0].candidate_count == 0
    assert "返回上層導覽" in collector.program_states[0].reason
    assert collector.diagnostic.completeness == "partial"
    assert collector.diagnostic.child_sources_succeeded == 0
