# -*- coding: utf-8 -*-

import json
from pathlib import Path

from src.ai.gemini_requirement_extractor import (
    GeminiRequirementExtraction,
    RequirementEvidence,
)
from src.automation.structured_shadow_artifact import write_structured_shadow_artifacts
from src.collectors.base_collector import BaseCollector
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ResourceDiagnostic,
    RULES_STATUS_NOT_REQUIRED,
)
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.evaluators.structured_eligibility_evaluator import StructuredEligibilityEvaluator
from src.models.scholarship import Scholarship
from src.notifiers.notification_dispatcher import NotificationFanout
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.gemini_fallback_service import GeminiAnalysisDiagnostic, GeminiUsageLimiter
from src.services.gemini_text_analysis_service import GeminiTextAnalysisResult
from src.services.scholarship_service import ScholarshipService


class FakeCollector(BaseCollector):
    def __init__(self, item: Scholarship) -> None:
        self.item = item

    def collect(self) -> list[Scholarship]:
        return [self.item]


class FakeDetailFetcher:
    def __init__(self, result: DetailFetchResult) -> None:
        self.result = result

    def fetch_with_diagnostics(self, _: Scholarship) -> DetailFetchResult:
        return self.result


class FakeTextAnalysis:
    def __init__(self, result: GeminiTextAnalysisResult) -> None:
        self.result = result
        self.limiter = GeminiUsageLimiter(3, 12000)

    def analyze(self, _: str, __: DetailFetchResult) -> GeminiTextAnalysisResult:
        return self.result


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
        research_keywords=("電子", "電力", "能源"),
    )


def _item() -> Scholarship:
    return Scholarship.from_raw(
        "lhu",
        "電力與能源獎學金申請",
        "2026-07-28",
        "https://example.com/scholarship",
    )


def _fetch_result(item: Scholarship) -> DetailFetchResult:
    body = "申請對象為大專在校生，電子工程相關科系可申請，學業平均80分以上。"
    source = ResourceDiagnostic(
        "source",
        item.source_url,
        item.source_url,
        "text/html",
        len(body.encode("utf-8")),
        "html",
        "success",
        len(body),
    )
    return DetailFetchResult(
        body,
        source,
        tuple(),
        0,
        body_text=body,
        rules_status=RULES_STATUS_NOT_REQUIRED,
    )


def _extraction() -> GeminiRequirementExtraction:
    return GeminiRequirementExtraction(
        document_type="scholarship_rules",
        criteria_complete=True,
        needs_more_pages=False,
        program_types_excluded=["進修部"],
        departments_included=["電子工程相關科系"],
        minimum_average_grade=80,
        evidence=[RequirementEvidence(page=1, text="本獎學金不受理進修部學生")],
    )


def _diagnostic(status: str = "text_success") -> GeminiAnalysisDiagnostic:
    return GeminiAnalysisDiagnostic(
        status,
        "https://example.com/scholarship",
        "test-model",
        False,
        0,
        100,
        20,
        120,
        "測試文字抽取完成。",
    )


def test_audit_keeps_legacy_and_records_structured_difference(tmp_path: Path) -> None:
    item = _item()
    text_result = GeminiTextAnalysisResult(_extraction(), _diagnostic())
    service = ScholarshipService(
        FakeCollector(item),
        ScholarshipRepository(tmp_path / "data" / "scholarships.db"),
        NotificationFanout(tuple()),
        include_keywords=("獎學金",),
        summary_batch_size=5,
        detail_fetcher=FakeDetailFetcher(_fetch_result(item)),
        evaluator=EligibilityEvaluator(),
        profile=_profile(),
        gemini_text_analysis=FakeTextAnalysis(text_result),
        structured_evaluator=StructuredEligibilityEvaluator(),
    )

    result = service.audit()

    assert result.eligible_count == 1
    assert result.structured_evaluated_count == 1
    assert result.structured_changed_count == 1
    record = result.records[0]
    assert record.item.eligibility_status == "eligible"
    assert record.structured_shadow is not None
    assert record.structured_shadow.structured_status == "ineligible"
    assert record.shadow_status == "compared"

    csv_path, json_path = write_structured_shadow_artifacts(result, tmp_path / "artifacts")
    assert csv_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["structured"]["changed"] == 1
    assert payload["records"][0]["legacy_status"] == "eligible"
    assert payload["records"][0]["structured_status"] == "ineligible"


def test_audit_marks_budget_deferred_for_next_run(tmp_path: Path) -> None:
    item = _item()
    deferred = GeminiTextAnalysisResult(None, _diagnostic("budget_deferred"))
    service = ScholarshipService(
        FakeCollector(item),
        ScholarshipRepository(tmp_path / "data" / "scholarships.db"),
        NotificationFanout(tuple()),
        include_keywords=("獎學金",),
        summary_batch_size=5,
        detail_fetcher=FakeDetailFetcher(_fetch_result(item)),
        evaluator=EligibilityEvaluator(),
        profile=_profile(),
        gemini_text_analysis=FakeTextAnalysis(deferred),
        structured_evaluator=StructuredEligibilityEvaluator(),
    )

    result = service.audit()

    assert result.structured_evaluated_count == 0
    assert result.structured_deferred_count == 1
    assert result.records[0].shadow_status == "budget_deferred"
    assert result.records[0].structured_shadow is None
