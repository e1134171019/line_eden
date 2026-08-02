# -*- coding: utf-8 -*-

from dataclasses import replace

import pytest

from src.catalogs.tun_live_contracts import LiveSourceCandidate
from src.catalogs.tun_program_sources import ResolvedProgramSource, resolved_programs
from src.collectors.collection_diagnostics import CollectionMode, CollectorDiagnostic
from src.collectors.listing_paginator import ListingCrawlResult, ListingPage
import src.collectors.resilient_tun_program_watch_collector as resilient_module
from src.collectors.resilient_tun_program_watch_collector import (
    ResilientTunProgramWatchCollector,
    _RetryAttempt,
    _RetryStats,
    _attempt_score,
    _fallback_url_type,
    _rebuild_diagnostic,
    _replace_program_records,
    _source_variants,
    _unique_records,
)
from src.collectors.tun_program_watch_collector import (
    PageDiscoveryDiagnostic,
    ProgramMatchObservation,
    ProgramSourceState,
    TunProgramWatchCollector,
)
from src.models.scholarship import Scholarship
from src.models.source_quality import SourceRisk, SourceUrlType


def _source(program_id: str) -> ResolvedProgramSource:
    return next(item for item in resolved_programs() if item.program_id == program_id)


def _state(
    source: ResolvedProgramSource,
    status: str,
    *,
    score: int = 0,
    count: int = 0,
) -> ProgramSourceState:
    return ProgramSourceState(
        source.program_id,
        source.title,
        source.official_url,
        status,
        candidate_count=count,
        source_url_type=source.source_url_type,
        update_risk=source.update_risk,
        top_score=score,
    )


# preferred 來源必須早於原入口與既有 fallback，且 URL 不重複。
def test_source_variants_prioritize_live_contract() -> None:
    source = _source("yonglin-hope")
    preferred = (
        LiveSourceCandidate(
            "https://service.utaipei.edu.tw/p/404-1034-133653.php?Lang=zh-tw",
            SourceUrlType.RELAY_DETAIL,
            "115年正式轉載",
        ),
    )

    variants = _source_variants(source, preferred)

    assert variants[0] == preferred[0]
    assert len({item.url for item in variants}) == len(variants)
    assert any(item.url == source.official_url for item in variants)


# 正式機構單篇 fallback 必須允許頁面自身成為候選。
def test_fallback_url_type_recognizes_relay_detail() -> None:
    value = _fallback_url_type(
        "https://service.utaipei.edu.tw/p/404-1034-130714.php?Lang=zh-tw",
        SourceUrlType.LIST,
    )

    assert value is SourceUrlType.RELAY_DETAIL
    assert (
        _fallback_url_type("https://example.org/posts/240", SourceUrlType.LIST)
        is SourceUrlType.ANNUAL_DETAIL
    )
    assert (
        _fallback_url_type("https://example.org/list", SourceUrlType.LIST)
        is SourceUrlType.LIST
    )


# force replace 必須移除同方案的錯頁候選，但保留其他方案。
def test_replace_program_records_removes_wrong_page_candidate() -> None:
    wrong = Scholarship.from_raw(
        "tun-program-songliang-aid",
        "台灣松樑教育公益促進協會助學金",
        "",
        "https://www.slceas.org.tw/index.php/scholarship",
        program_id="songliang-aid",
    )
    correct = Scholarship.from_raw(
        "tun-program-songliang-aid",
        "助學金實施辦法",
        "",
        "https://www.slceas.org.tw/index.php/scholarship/scholarship01",
        program_id="songliang-aid",
    )
    other = Scholarship.from_raw(
        "other",
        "其他獎學金",
        "2026-01-01",
        "https://example.org/other",
        program_id="other",
    )

    result = _replace_program_records(
        [wrong, other],
        "songliang-aid",
        (correct, correct),
        True,
    )

    assert wrong not in result
    assert result.count(correct) == 1
    assert other in result


# retry 依序嘗試來源，第一個 matched 即停止並回傳。
def test_retry_program_uses_best_live_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source("tf4dr-aid")
    collector = ResilientTunProgramWatchCollector(
        1,
        "test-agent",
        CollectionMode.INCREMENTAL,
        1,
        1,
    )
    candidates = (
        LiveSourceCandidate("https://example.org/one", SourceUrlType.LIST, "one"),
        LiveSourceCandidate("https://example.org/two", SourceUrlType.LIST, "two"),
        LiveSourceCandidate("https://example.org/three", SourceUrlType.LIST, "three"),
    )
    record = Scholarship.from_raw(
        "tun-program-tf4dr-aid",
        "第2學期助學金",
        "2026-02-10",
        "https://example.org/two/detail",
        program_id="tf4dr-aid",
    )
    attempts = [
        _RetryAttempt(_state(source, "matcher_miss", score=65), tuple()),
        _RetryAttempt(_state(source, "matched", score=115, count=1), (record,)),
    ]
    seen: list[str] = []

    monkeypatch.setattr(resilient_module, "_source_variants", lambda *_: candidates)

    def fake_collect_variant(
        _program: ResolvedProgramSource,
        reason: str,
        _stats: _RetryStats,
    ) -> _RetryAttempt:
        seen.append(reason)
        return attempts.pop(0)

    monkeypatch.setattr(collector, "_collect_variant", fake_collect_variant)

    result = collector._retry_program(source, _RetryStats())

    assert result is not None
    assert result.state.status == "matched"
    assert result.records == (record,)
    assert seen == ["one", "two"]


# 全部 fallback 未命中時保留分數最高、狀態最接近成功的結果。
def test_retry_program_returns_best_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source("tf4dr-aid")
    collector = ResilientTunProgramWatchCollector(1, "ua")
    candidates = (
        LiveSourceCandidate("https://example.org/a", SourceUrlType.LIST, "a"),
        LiveSourceCandidate("https://example.org/b", SourceUrlType.LIST, "b"),
    )
    attempts = [
        _RetryAttempt(_state(source, "fetch_failed"), tuple()),
        _RetryAttempt(_state(source, "matcher_miss", score=70), tuple()),
    ]
    monkeypatch.setattr(resilient_module, "_source_variants", lambda *_: candidates)
    monkeypatch.setattr(
        collector,
        "_collect_variant",
        lambda *_: attempts.pop(0),
    )

    result = collector._retry_program(source, _RetryStats())

    assert result is not None
    assert result.state.status == "matcher_miss"
    assert _attempt_score(result) > _attempt_score(
        _RetryAttempt(_state(source, "fetch_failed"), tuple())
    )


# 單一入口重用既有 parser 與狀態機，並累計 live retry 統計。
def test_collect_variant_builds_matched_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = replace(
        _source("tf4dr-aid"),
        aliases=("第2學期助學金",),
        official_url="https://example.org/posts/240",
        source_url_type=SourceUrlType.ANNUAL_DETAIL,
    )
    collector = ResilientTunProgramWatchCollector(1, "ua")
    page = ListingPage(source.official_url, "<h1>第2學期助學金</h1>")
    crawl = ListingCrawlResult(
        (page,),
        1,
        1,
        1,
        "complete",
        "all_detected_pages_completed",
        tuple(),
    )
    record = Scholarship.from_raw(
        "tun-program-tf4dr-aid",
        "第2學期助學金",
        "2026-02-10",
        source.official_url,
        program_id=source.program_id,
    )
    discovery = PageDiscoveryDiagnostic(
        {
            source.program_id: ProgramMatchObservation(
                raw_candidates=1,
                top_score=100,
                match_method="exact_alias",
            )
        },
        generic_candidates=1,
        link_candidates=0,
    )
    monkeypatch.setattr(resilient_module, "crawl_listing_pages", lambda *_args, **_kw: crawl)
    monkeypatch.setattr(
        resilient_module,
        "_extract_program_notices_with_diagnostics",
        lambda *_args: ([record], 1, {source.program_id: 1}, discovery),
    )
    stats = _RetryStats()

    result = collector._collect_variant(source, "fixture", stats)

    assert result.state.status == "matched"
    assert result.records == (record,)
    assert "production fallback：fixture" in result.state.reason
    assert stats.pages_requested == 1
    assert stats.pages_succeeded == 1
    assert stats.raw_matches == 1
    assert stats.parsed_records == 1


# 正式 collect 必須先刪除 force-replace 錯頁，再加入 fallback 候選。
def test_collect_replaces_wrong_records_and_updates_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    songliang = _source("songliang-aid")
    tf4dr = _source("tf4dr-aid")
    wrong = Scholarship.from_raw(
        "tun-program-songliang-aid",
        "台灣松樑教育公益促進協會助學金",
        "",
        songliang.official_url,
        program_id=songliang.program_id,
    )
    correct = Scholarship.from_raw(
        "tun-program-songliang-aid",
        "助學金實施辦法",
        "",
        "https://www.slceas.org.tw/index.php/scholarship/scholarship01",
        program_id=songliang.program_id,
    )
    tf_record = Scholarship.from_raw(
        "tun-program-tf4dr-aid",
        "第2學期助學金",
        "2026-02-10",
        "https://www.tf4dr.org/posts/240",
        program_id=tf4dr.program_id,
    )

    def fake_base_collect(instance: TunProgramWatchCollector) -> list[Scholarship]:
        instance.program_states = (
            _state(songliang, "matched", score=115, count=1),
            _state(tf4dr, "matcher_miss", score=65),
        )
        instance.diagnostic = CollectorDiagnostic(
            completeness="partial",
            pages_detected=2,
            pages_requested=2,
            pages_succeeded=2,
            raw_rows=2,
            parsed_rows=1,
            rejected_rows=1,
            child_sources_detected=2,
            child_sources_succeeded=1,
        )
        return [wrong]

    monkeypatch.setattr(TunProgramWatchCollector, "collect", fake_base_collect)
    monkeypatch.setattr(
        resilient_module,
        "resolved_programs",
        lambda: (songliang, tf4dr),
    )

    def fake_retry(
        _instance: ResilientTunProgramWatchCollector,
        source: ResolvedProgramSource,
        _stats: _RetryStats,
    ) -> _RetryAttempt:
        if source.program_id == songliang.program_id:
            return _RetryAttempt(
                _state(songliang, "matched", score=115, count=1),
                (correct,),
            )
        return _RetryAttempt(
            _state(tf4dr, "matched", score=115, count=1),
            (tf_record,),
        )

    monkeypatch.setattr(
        ResilientTunProgramWatchCollector,
        "_retry_program",
        fake_retry,
    )
    collector = ResilientTunProgramWatchCollector(1, "ua")

    records = collector.collect()

    assert wrong not in records
    assert correct in records
    assert tf_record in records
    assert {item.status for item in collector.program_states} == {"matched"}
    assert collector.diagnostic.child_sources_succeeded == 2


# force replace 的 fallback 即使失敗，也不能讓舊錯頁候選留在管線。
def test_collect_drops_wrong_record_when_forced_fallback_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    songliang = _source("songliang-aid")
    wrong = Scholarship.from_raw(
        "tun-program-songliang-aid",
        "台灣松樑教育公益促進協會助學金",
        "",
        songliang.official_url,
        program_id=songliang.program_id,
    )

    def fake_base_collect(instance: TunProgramWatchCollector) -> list[Scholarship]:
        instance.program_states = (_state(songliang, "matched", score=115, count=1),)
        instance.diagnostic = CollectorDiagnostic(
            completeness="complete",
            pages_detected=1,
            pages_requested=1,
            pages_succeeded=1,
            child_sources_detected=1,
            child_sources_succeeded=1,
        )
        return [wrong]

    monkeypatch.setattr(TunProgramWatchCollector, "collect", fake_base_collect)
    monkeypatch.setattr(resilient_module, "resolved_programs", lambda: (songliang,))
    monkeypatch.setattr(
        ResilientTunProgramWatchCollector,
        "_retry_program",
        lambda *_: _RetryAttempt(_state(songliang, "fetch_failed"), tuple()),
    )
    collector = ResilientTunProgramWatchCollector(1, "ua")

    records = collector.collect()

    assert records == []
    assert collector.program_states[0].status == "fetch_failed"
    assert collector.diagnostic.completeness == "partial"


# 同一 fallback 多個節點依 content hash 去重。
def test_unique_records_deduplicates_same_announcement() -> None:
    item = Scholarship.from_raw(
        "tun-program-tf4dr-aid",
        "第2學期助學金",
        "2026-02-10",
        "https://www.tf4dr.org/posts/240",
        program_id="tf4dr-aid",
    )

    assert _unique_records([item, item]) == [item]


# 最後仍為 matcher miss 時，來源群組必須維持 partial 並扣除成功子來源。
def test_rebuild_diagnostic_uses_final_program_states() -> None:
    base = CollectorDiagnostic(
        completeness="partial",
        pages_detected=38,
        pages_requested=38,
        pages_succeeded=31,
        raw_rows=100,
        parsed_rows=80,
        rejected_rows=20,
        stop_reason="program_watch_partial",
        child_sources_detected=38,
        child_sources_succeeded=31,
    )
    states = tuple(
        ProgramSourceState(
            f"program-{index}",
            f"方案{index}",
            "https://example.org",
            "matcher_miss" if index == 0 else "matched",
            source_url_type=SourceUrlType.LIST,
            update_risk=SourceRisk.LOW,
        )
        for index in range(38)
    )

    rebuilt = _rebuild_diagnostic(base, states, _RetryStats())

    assert rebuilt.completeness == "partial"
    assert rebuilt.child_sources_succeeded == 37
    assert "program-0:matcher_miss" in rebuilt.error


# 全部技術失敗解除後，成功子來源應回到 38。
def test_rebuild_diagnostic_marks_all_children_successful() -> None:
    base = CollectorDiagnostic(
        completeness="complete",
        pages_detected=38,
        pages_requested=38,
        pages_succeeded=38,
        child_sources_detected=38,
        child_sources_succeeded=38,
    )
    states = tuple(
        ProgramSourceState(
            f"program-{index}",
            f"方案{index}",
            "https://example.org",
            "no_current_announcement" if index == 0 else "matched",
            source_url_type=SourceUrlType.LIST,
            update_risk=SourceRisk.LOW,
        )
        for index in range(38)
    )

    rebuilt = _rebuild_diagnostic(base, states, _RetryStats())

    assert rebuilt.child_sources_succeeded == 38
    assert rebuilt.error == ""
    assert rebuilt.stop_reason == "program_watch_live_contract_passed"
