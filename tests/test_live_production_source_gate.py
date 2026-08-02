# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest

from src.catalogs.live_program_sources import live_resolved_programs
from src.catalogs.tun_program_sources import ResolvedProgramSource
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.listing_paginator import ListingCrawlResult, ListingPage
import src.collectors.resilient_tun_program_watch_collector as resilient
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.evaluators.application_evidence_scorer import ApplicationEvidence
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    EligibilityDecision,
)
from src.evaluators.notice_classifier import APPLICATION
from src.matchers.program_name_matcher import match_program
from src.models.eligibility_axes import VERIFY_SOURCE
from src.models.scholarship import Scholarship
from src.models.source_quality import SourceRisk, SourceUrlType
from src.profiles.student_profile import StudentProfile
from src.services.revision_aware_scholarship_service import (
    RevisionAwareScholarshipService,
)
from src.services.scholarship_service import EvaluationOutcome


class _UnusedFetcher:
    def fetch_one(self, url: str) -> str:
        raise AssertionError(f"測試不應真的抓取 {url}")

    def fetch_many(
        self,
        urls: tuple[str, ...],
    ) -> tuple[dict[str, str], dict[str, str]]:
        raise AssertionError(f"測試不應真的批次抓取 {urls}")


class _TextAnalysis:
    def __init__(self) -> None:
        self.extraction = object()

    def analyze(self, title: str, fetch_result: DetailFetchResult) -> SimpleNamespace:
        return SimpleNamespace(extraction=self.extraction)


class _StructuredEvaluator:
    def __init__(self, status: str) -> None:
        self.status = status

    def evaluate(self, extraction: object, profile: StudentProfile) -> SimpleNamespace:
        reason = "須具備以下任一身分：家庭清寒、經濟弱勢、遭逢變故。"
        return SimpleNamespace(decision=EligibilityDecision(self.status, (reason,)))


def _source(program_id: str = "tf4dr-aid") -> ResolvedProgramSource:
    return ResolvedProgramSource(
        program_id,
        "賑災基金會助學金",
        "財團法人賑災基金會",
        ("賑災基金會助學金", "學年度第2學期助學金"),
        "https://primary.example/posts",
        "verified",
        "tf4dr-foundation",
        SourceUrlType.LIST,
        ("primary.example", "fallback.example"),
        "測試 fallback。",
        SourceRisk.LOW,
        ("https://fallback.example/posts",),
        "2026-08-02",
    )


def _sunshine_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(
        item
        for item in live_resolved_programs()
        if item.program_id in {"sunshine-scholarship", "sunshine-wanzu"}
    )


def _failed_crawl(url: str) -> ListingCrawlResult:
    return ListingCrawlResult(
        tuple(),
        1,
        1,
        0,
        "partial",
        "entry_fetch_failed",
        (f"{url}（連線失敗）",),
    )


def _success_crawl(url: str) -> ListingCrawlResult:
    html = """
    <ul>
      <li>
        <span>2026/02/10</span>
        <a href="/posts/240">本會114學年度第2學期「助學金」開始申請</a>
      </li>
    </ul>
    """
    return ListingCrawlResult(
        (ListingPage(url, html),),
        1,
        1,
        1,
        "complete",
        "all_detected_pages_completed",
        tuple(),
    )


def _profile() -> StudentProfile:
    return StudentProfile(
        school="龍華科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.34,
        conduct_grade=86,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電力電子",),
    )


def _fetch_result() -> DetailFetchResult:
    text = "申請資格：須具備家庭清寒、經濟弱勢或遭逢變故其中一項。"
    source = ResourceDiagnostic(
        "source",
        "https://example.test/detail",
        "https://example.test/detail",
        "text/html",
        len(text.encode("utf-8")),
        "html",
        "success",
        len(text),
    )
    return DetailFetchResult(text, source, tuple(), 0, body_text=text)


def _outcome(status: str) -> EvaluationOutcome:
    return EvaluationOutcome(
        EligibilityDecision(status, ("legacy 判斷。",)),
        APPLICATION,
        "open",
        "申請資格正文",
        None,
        ApplicationEvidence(0, "navigation_or_wrong_page", tuple()),
        VERIFY_SOURCE,
    )


def test_primary_failure_uses_fallback_and_creates_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = "https://primary.example/posts"
    fallback = "https://fallback.example/posts"

    def fake_crawl(
        entry_url: str,
        collection_mode: CollectionMode,
        max_pages: int,
        fetch_text: object,
        fetch_many: object,
    ) -> ListingCrawlResult:
        _ = collection_mode, max_pages, fetch_text, fetch_many
        return _failed_crawl(entry_url) if entry_url == primary else _success_crawl(entry_url)

    monkeypatch.setattr(resilient, "crawl_listing_pages", fake_crawl)

    result = resilient._collect_program_group(
        primary,
        (_source(),),
        CollectionMode.FULL_AUDIT,
        20,
        _UnusedFetcher(),  # type: ignore[arg-type]
    )

    assert result.fallback_used is True
    assert result.counts == {"tf4dr-aid": 1}
    assert len(result.records) == 1
    assert result.records[0].entry_url == fallback
    assert result.crawl.pages
    assert result.crawl.errors == tuple()


def test_all_source_candidates_failed_remains_fetch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resilient,
        "crawl_listing_pages",
        lambda entry_url, *args, **kwargs: _failed_crawl(entry_url),
    )

    result = resilient._collect_program_group(
        "https://primary.example/posts",
        (_source(),),
        CollectionMode.FULL_AUDIT,
        20,
        _UnusedFetcher(),  # type: ignore[arg-type]
    )

    assert result.records == tuple()
    assert result.crawl.pages == tuple()
    assert len(result.crawl.errors) == 2


@pytest.mark.parametrize(
    ("program_id", "title"),
    (
        ("tf4dr-aid", "本會114學年度第2學期『助學金』自115年2月10日起受理"),
        ("hsinrong-emergency-aid", "竹山欣榮圖書館急難學生助學金"),
        ("lijin-taoyuan", "114年度清寒獎助學金開放申請"),
        (
            "lovepeace-disadvantaged",
            "財團法人祥和文教基金會114年度優秀清寒獎學金獎助學金",
        ),
    ),
)
def test_live_titles_match_program(program_id: str, title: str) -> None:
    program = next(
        item for item in live_resolved_programs() if item.program_id == program_id
    )

    assert match_program(title, program).matched is True


def test_sunshine_shared_announcement_fans_out_to_both_programs() -> None:
    html = """
    <div class="news-row">
      <a href="/news/announce/news20250814">
        〖重要提醒〗114年度獎助學金相關簡章開放下載
      </a>
      <span>2025.08.14</span>
    </div>
    """

    records = resilient._shared_announcement_records(
        html,
        "https://www.sunshine.org.tw/news/announce/0/10",
        "https://www.sunshine.org.tw/news/announce/0/10",
        _sunshine_programs(),
    )

    assert {item.program_id for item in records} == {
        "sunshine-scholarship",
        "sunshine-wanzu",
    }
    assert {item.match_method for item in records} == {"shared_announcement"}
    assert {item.detail_url for item in records} == {
        "https://www.sunshine.org.tw/news/announce/news20250814"
    }


def test_sunshine_application_page_fans_out_when_main_site_times_out() -> None:
    html = """
    <html>
      <head><title>陽光基金會獎助學金申請系統</title></head>
      <body><div id="app"></div></body>
    </html>
    """

    records = resilient._shared_announcement_records(
        html,
        "https://scls.sunshine.org.tw/",
        "https://scls.sunshine.org.tw/",
        _sunshine_programs(),
    )

    assert {item.program_id for item in records} == {
        "sunshine-scholarship",
        "sunshine-wanzu",
    }
    assert {item.match_method for item in records} == {"shared_application_page"}
    assert {item.detail_url for item in records} == {
        "https://scls.sunshine.org.tw/"
    }


def test_live_source_overrides_replace_broken_primary_urls() -> None:
    programs = {item.program_id: item for item in live_resolved_programs()}

    assert programs["buddha-charity-progress"].official_url.startswith(
        "https://www.cksh.tp.edu.tw/"
    )
    assert programs["yonglin-hope"].source_url_type == SourceUrlType.RELAY_LIST
    assert programs["sunshine-scholarship"].official_url == (
        "https://www.sunshine.org.tw/news/announce/0/10"
    )
    sunshine_fallbacks = programs["sunshine-scholarship"].fallback_urls
    assert sunshine_fallbacks[0] == "https://scls.sunshine.org.tw/"
    assert (
        "https://announce.yzu.edu.tw/index.php/tw/st/st-lgs20250828-1100-01"
        in sunshine_fallbacks
    )
    assert sunshine_fallbacks[-1] == (
        "https://www.sunshine.org.tw/news/announce/0/20"
    )
    assert programs["lovepeace-disadvantaged"].source_url_type == (
        SourceUrlType.RELAY_DETAIL
    )
    assert programs["dapeng-aid"].official_url.startswith(
        "https://osa.ndhu.edu.tw/"
    )


def test_structured_ineligible_vetoes_legacy_eligible() -> None:
    service = object.__new__(RevisionAwareScholarshipService)
    service.gemini_text_analysis = _TextAnalysis()
    service.structured_evaluator = _StructuredEvaluator(INELIGIBLE)
    service.profile = _profile()
    item = Scholarship.from_raw(
        "test",
        "松樑助學金開放申請",
        "2026-08-01",
        "https://example.test/detail",
    )

    result = service._apply_structured_ineligible_veto(
        item,
        _fetch_result(),
        _outcome(ELIGIBLE),
    )

    assert result.decision.status == INELIGIBLE
    assert result.action_status == "reject"


def test_structured_result_never_promotes_legacy_review() -> None:
    service = object.__new__(RevisionAwareScholarshipService)
    service.gemini_text_analysis = _TextAnalysis()
    service.structured_evaluator = _StructuredEvaluator(ELIGIBLE)
    service.profile = _profile()
    item = Scholarship.from_raw(
        "test",
        "一般獎學金開放申請",
        "2026-08-01",
        "https://example.test/detail",
    )

    result = service._apply_structured_ineligible_veto(
        item,
        _fetch_result(),
        _outcome(REVIEW),
    )

    assert result.decision.status == REVIEW
