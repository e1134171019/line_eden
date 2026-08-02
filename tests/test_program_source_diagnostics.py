# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import ScholarshipProgramWatch
from src.catalogs.tun_program_sources import ResolvedProgramSource, resolved_programs
from src.collectors.listing_paginator import ListingCrawlResult, ListingPage
from src.collectors.tun_program_watch_collector import (
    PageDiscoveryDiagnostic,
    ProgramMatchObservation,
    _extract_program_notices_with_diagnostics,
    _initial_program_state,
    _program_crawl_status,
)
from src.models.source_quality import SourceRisk, SourceUrlType


def _program(
    program_id: str = "test",
    url_type: SourceUrlType = SourceUrlType.LIST,
) -> ResolvedProgramSource:
    return ResolvedProgramSource(
        program_id,
        "測試人才獎學金",
        "測試基金會",
        ("測試人才獎學金",),
        "https://foundation.example/news",
        "verified",
        "test-foundation",
        url_type,
        ("foundation.example",),
        "測試來源。",
        SourceRisk.LOW,
        tuple(),
        "2026-08-02",
    )


def _crawl() -> ListingCrawlResult:
    page = ListingPage("https://foundation.example/news", "<html></html>")
    return ListingCrawlResult(
        (page,),
        1,
        1,
        1,
        "complete",
        "all_detected_pages_completed",
        tuple(),
    )


def _diagnostic(
    observation: ProgramMatchObservation | None = None,
    *,
    generic: int = 0,
    links: int = 1,
) -> PageDiscoveryDiagnostic:
    return PageDiscoveryDiagnostic(
        {"test": observation or ProgramMatchObservation()},
        generic,
        links,
    )


def test_no_current_announcement_is_not_reported_as_failure() -> None:
    status, reason = _program_crawl_status(
        _program(),
        _crawl(),
        0,
        ProgramMatchObservation(),
        _diagnostic(),
        1,
    )

    assert status == "no_current_announcement"
    assert "結構正常" in reason


def test_partial_score_is_reported_as_matcher_miss() -> None:
    observation = ProgramMatchObservation(
        raw_candidates=1,
        top_score=70,
        second_best_score=10,
        match_method="core_terms",
    )

    status, reason = _program_crawl_status(
        _program(),
        _crawl(),
        0,
        observation,
        _diagnostic(observation),
        1,
    )

    assert status == "matcher_miss"
    assert "最高分 70" in reason


def test_close_sibling_scores_are_reported_as_ambiguous() -> None:
    observation = ProgramMatchObservation(
        raw_candidates=1,
        ambiguous_candidates=1,
        top_score=115,
        second_best_score=110,
        match_method="ambiguous",
        competing_program_id="sibling",
    )

    status, reason = _program_crawl_status(
        _program(),
        _crawl(),
        0,
        observation,
        _diagnostic(observation),
        2,
    )

    assert status == "match_ambiguous"
    assert "競爭方案 sibling" in reason


def test_missing_links_on_list_page_are_structure_change() -> None:
    status, _ = _program_crawl_status(
        _program(),
        _crawl(),
        0,
        ProgramMatchObservation(),
        _diagnostic(links=0),
        1,
    )

    assert status == "source_structure_changed"


def test_generic_candidates_on_single_program_source_are_matcher_miss() -> None:
    status, reason = _program_crawl_status(
        _program(),
        _crawl(),
        0,
        ProgramMatchObservation(),
        _diagnostic(generic=3),
        1,
    )

    assert status == "matcher_miss"
    assert "3 個一般獎助候選" in reason


def test_blocked_url_types_have_explicit_initial_states() -> None:
    portal = _initial_program_state(_program("portal", SourceUrlType.APPLICATION_PORTAL))
    wrong = _initial_program_state(_program("wrong", SourceUrlType.WRONG))

    assert portal.status == "application_portal"
    assert wrong.status == "wrong_source"


def test_collector_uses_sibling_competition_for_auden() -> None:
    programs = tuple(
        item for item in resolved_programs() if item.organizer_id == "auden-foundation"
    )
    html = """
    <ul>
      <li>
        <span>2026/07/23</span>
        <a href="/2026scholarship/">2026耀登炳南大專院校優秀人才獎學金</a>
      </li>
    </ul>
    """

    records, _, counts, diagnostic = _extract_program_notices_with_diagnostics(
        html,
        "https://www.auden.com.tw/news-4/",
        "https://www.auden.com.tw/news-4/",
        programs,
    )

    assert len(records) == 1
    assert records[0].program_id == "auden-university-talent"
    assert counts == {"auden-university-talent": 1}
    assert diagnostic.observations["auden-university-talent"].top_score > 0
    assert diagnostic.observations["auden-innovation-research"].top_score == 0


def test_ambiguous_siblings_do_not_create_scholarship_record() -> None:
    programs = (
        ScholarshipProgramWatch(
            "same-one",
            "共同人才獎學金",
            "共同基金會",
            ("共同人才獎學金",),
            "https://example.test/news",
            "verified",
        ),
        ScholarshipProgramWatch(
            "same-two",
            "共同人才獎學金二",
            "共同基金會",
            ("共同人才獎學金",),
            "https://example.test/news",
            "verified",
        ),
    )
    html = "<a href='/detail'>共同人才獎學金申請公告</a>"

    records, _, counts, diagnostic = _extract_program_notices_with_diagnostics(
        html,
        "https://example.test/news",
        "https://example.test/news",
        programs,
    )

    assert records == []
    assert counts == {}
    assert sum(
        item.ambiguous_candidates for item in diagnostic.observations.values()
    ) == 2
