# -*- coding: utf-8 -*-

from pathlib import Path

from src.collectors.base_collector import BaseCollector
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ResourceDiagnostic,
    RULES_STATUS_DISCOVERED_UNRESOLVED,
)
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.gemini_fallback_service import (
    GeminiAnalysisDiagnostic,
    GeminiFallbackResult,
    GeminiUsageSummary,
)
from src.services.scholarship_service import ScholarshipService


class FakeCollector(BaseCollector):
    def __init__(self, item: Scholarship) -> None:
        self.item = item

    def collect(self) -> list[Scholarship]:
        return [self.item]


class FakeDiagnosticFetcher:
    def fetch_with_diagnostics(self, item: Scholarship) -> DetailFetchResult:
        source = ResourceDiagnostic(
            "source", item.source_url, item.source_url, "text/html",
            100, "html", "success", 20, "",
        )
        attachment = ResourceDiagnostic(
            "attachment", "https://example.com/rules.pdf",
            "https://example.com/rules.pdf", "application/pdf",
            1000, "pdf", "error", 0, "PDF 沒有可擷取文字，可能是掃描檔",
            "rules", "申請辦法",
        )
        body = "申請資格請參閱附件。"
        return DetailFetchResult(
            body,
            source,
            (attachment,),
            1,
            body_text=body,
            rules_status=RULES_STATUS_DISCOVERED_UNRESOLVED,
        )


class FakeGeminiFallback:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, title: str, fetch_result: DetailFetchResult) -> GeminiFallbackResult:
        self.calls += 1
        diagnostic = GeminiAnalysisDiagnostic(
            "success", "https://example.com/rules.pdf", "gemini-test",
            False, 2, 300, 50, 350, "已抽取完整資格條件。",
        )
        return GeminiFallbackResult(
            "申請對象為大專院校在校生。學業平均80分以上。",
            diagnostic,
        )

    def usage_summary(self) -> GeminiUsageSummary:
        return GeminiUsageSummary(self.calls, 0, 300 if self.calls else 0, 50 if self.calls else 0)


def _profile() -> StudentProfile:
    return StudentProfile(
        school="測試科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.34,
        conduct_grade=85,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("能源",),
    )


def _service(
    tmp_path: Path,
    item: Scholarship,
    fallback: FakeGeminiFallback,
) -> ScholarshipService:
    return ScholarshipService(
        FakeCollector(item),
        ScholarshipRepository(tmp_path / "scholarships.db"),
        lambda _: None,
        include_keywords=("獎學金",),
        summary_batch_size=5,
        detail_fetcher=FakeDiagnosticFetcher(),
        evaluator=EligibilityEvaluator(),
        profile=_profile(),
        gemini_fallback=fallback,
    )


def test_review_scanned_pdf_can_be_resolved_by_gemini(tmp_path: Path) -> None:
    item = Scholarship.from_raw(
        "lhu", "能源工程獎學金", "2026-07-27", "https://example.com/item",
    )
    fallback = FakeGeminiFallback()

    result = _service(tmp_path, item, fallback).audit()

    assert result.eligible_count == 1
    assert result.gemini_calls == 1
    assert result.records[0].gemini_diagnostic is not None


def test_local_ineligible_decision_skips_gemini(tmp_path: Path) -> None:
    item = Scholarship.from_raw(
        "lhu", "新住民子女獎學金", "2026-07-27", "https://example.com/item",
    )
    fallback = FakeGeminiFallback()

    result = _service(tmp_path, item, fallback).audit()

    assert result.ineligible_count == 1
    assert fallback.calls == 0
    assert result.records[0].gemini_diagnostic is None
