# -*- coding: utf-8 -*-

from dataclasses import replace

from src.catalogs.live_tun_sources import (
    live_resolved_programs,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.listing_paginator import ListingCrawlResult, ListingPage
from src.collectors.resilient_tun_program_watch_collector import (
    ResilientTunProgramWatchCollector,
)
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.evaluators.eligibility_evaluator import ELIGIBLE, INELIGIBLE
from src.evaluators.structured_eligibility_evaluator import ConditionResult
from src.matchers.program_name_matcher import match_programs
from src.models.eligibility_axes import VERIFY_SOURCE
from src.models.scholarship import Scholarship
from src.models.source_quality import SourceUrlType
from src.services.scholarship_service import (
    AuditRecord,
    AuditResult,
    PipelineCounts,
)
from src.services.structured_ineligible_veto import apply_veto_to_audit_result
from src.services.structured_shadow_comparison import StructuredShadowComparison


def _program(program_id: str):
    return next(item for item in live_resolved_programs() if item.program_id == program_id)


def test_live_source_overrides_avoid_known_production_failures() -> None:
    yonglin = _program("yonglin-hope")
    sunshine = _program("sunshine-scholarship")
    wanzu = _program("sunshine-wanzu")
    dapeng = _program("dapeng-aid")

    assert yonglin.source_url_type is SourceUrlType.RELAY_DETAIL
    assert "service.utaipei.edu.tw" in yonglin.official_url
    assert sunshine.source_url_type is SourceUrlType.EVERGREEN
    assert sunshine.official_url == "https://scls.sunshine.org.tw/"
    assert wanzu.source_url_type is SourceUrlType.RELAY_DETAIL
    assert "announce.yzu.edu.tw" in wanzu.official_url
    assert "osa.ndhu.edu.tw" in dapeng.official_url


def test_live_titles_match_three_previous_matcher_misses() -> None:
    cases = (
        (
            "tf4dr-aid",
            "本會114學年度第2學期『助學金』自115年2月10日起受理申請",
        ),
        (
            "hsinrong-emergency-aid",
            "竹山欣榮圖書館急難學生助學金",
        ),
        (
            "lovepeace-disadvantaged",
            "財團法人祥和文教基金會114年獎助學金-申請辦法",
        ),
    )
    for program_id, title in cases:
        program = _program(program_id)
        result = match_programs(title, (program,))
        assert result.matched, f"{program_id} 未命中：{result}"


def test_resilient_collector_uses_fallback_when_primary_fails(monkeypatch) -> None:
    import src.collectors.resilient_tun_program_watch_collector as module

    original = _program("tf4dr-aid")
    program = replace(
        original,
        official_url="https://primary.example/list",
        fallback_urls=("https://fallback.example/list",),
    )
    monkeypatch.setattr(module, "live_monitorable_programs", lambda: (program,))
    monkeypatch.setattr(module, "live_resolved_programs", lambda: (program,))

    def fake_crawl(url, *_args, **_kwargs):
        if url.startswith("https://primary.example"):
            return ListingCrawlResult(
                tuple(),
                1,
                1,
                0,
                "failed",
                "entry_fetch_failed",
                ("primary failed",),
            )
        html = (
            '<a href="/posts/240">本會114學年度第2學期「助學金」'
            "自115年2月10日起受理申請</a>"
        )
        return ListingCrawlResult(
            (ListingPage(url, html),),
            1,
            1,
            1,
            "complete",
            "all_detected_pages_completed",
            tuple(),
        )

    monkeypatch.setattr(module, "crawl_listing_pages", fake_crawl)
    collector = ResilientTunProgramWatchCollector(
        1.0,
        "test-agent",
        CollectionMode.FULL_AUDIT,
        2,
        1,
    )

    records = collector.collect()

    assert len(records) == 1
    assert records[0].program_id == "tf4dr-aid"
    assert collector.program_states[0].status == "matched"
    assert collector.program_states[0].entry_url == "https://fallback.example/list"
    assert "已使用 fallback" in collector.program_states[0].reason


def test_structured_hard_failure_vetoes_legacy_eligible() -> None:
    base = Scholarship.from_raw(
        "tun-program-songliang-aid",
        "台灣松樑教育公益促進協會助學金",
        "",
        "https://www.slceas.org.tw/index.php/scholarship",
        program_id="songliang-aid",
    )
    item = replace(
        base,
        notice_kind="application",
        application_status="deadline_unknown",
        eligibility_status=ELIGIBLE,
        eligibility_reason="公告領域符合。",
        hard_eligibility_status=ELIGIBLE,
        hard_eligibility_reason="公告領域符合。",
        action_status=VERIFY_SOURCE,
        resolution_status="navigation_or_wrong_page",
    )
    source = ResourceDiagnostic(
        "source",
        item.source_url,
        item.source_url,
        "text/html",
        100,
        "html",
        "success",
        20,
        "",
    )
    fetch_result = DetailFetchResult("", source, tuple(), 0)
    shadow = StructuredShadowComparison(
        ELIGIBLE,
        INELIGIBLE,
        True,
        "公告領域符合。",
        "須具備以下任一身分：家庭清寒、經濟弱勢、遭逢變故。",
        (
            ConditionResult(
                "special_status_any_of",
                "家庭清寒、經濟弱勢、遭逢變故",
                "fail",
                "須具備以下任一身分：家庭清寒、經濟弱勢、遭逢變故。",
            ),
        ),
    )
    record = AuditRecord(item, "", fetch_result, structured_shadow=shadow)
    result = AuditResult(
        [record],
        1,
        0,
        0,
        "test",
        pipeline_counts=PipelineCounts(
            raw_collected=1,
            relevance_accepted=1,
            stored_candidates=1,
            evaluated_pending=1,
            application=1,
            notifiable=1,
        ),
    )

    updated = apply_veto_to_audit_result(result)

    assert updated.eligible_count == 0
    assert updated.ineligible_count == 1
    assert updated.pipeline_counts.notifiable == 0
    assert updated.records[0].item.hard_eligibility_status == INELIGIBLE
    assert "家庭清寒" in updated.records[0].item.hard_eligibility_reason
