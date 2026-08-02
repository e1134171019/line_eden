# -*- coding: utf-8 -*-

from dataclasses import replace

from src.catalogs.tun_live_contracts import LiveSourceCandidate
from src.catalogs.tun_program_sources import resolved_programs
from src.collectors.collection_diagnostics import CollectorDiagnostic
from src.collectors.resilient_tun_program_watch_collector import (
    _RetryStats,
    _fallback_url_type,
    _rebuild_diagnostic,
    _replace_program_records,
    _source_variants,
)
from src.collectors.tun_program_watch_collector import ProgramSourceState
from src.models.scholarship import Scholarship
from src.models.source_quality import SourceRisk, SourceUrlType


# preferred 來源必須早於原入口與既有 fallback，且 URL 不重複。
def test_source_variants_prioritize_live_contract() -> None:
    source = next(item for item in resolved_programs() if item.program_id == "yonglin-hope")
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
        (correct,),
        True,
    )

    assert wrong not in result
    assert correct in result
    assert other in result


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
