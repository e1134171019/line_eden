# -*- coding: utf-8 -*-

from pathlib import Path
from types import SimpleNamespace

from src.ai.gemini_requirement_extractor import GeminiRequirementExtractor
from src.collectors.base_collector import BaseCollector
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ResourceDiagnostic,
    RULES_STATUS_NOT_REQUIRED,
)
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.gemini_cache_repository import GeminiCacheRepository
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.gemini_fallback_service import GeminiFallbackService, GeminiUsageLimiter
from src.services.scholarship_service import ScholarshipService


class FakeCollector(BaseCollector):
    def __init__(self, item: Scholarship) -> None:
        self.item = item

    def collect(self) -> list[Scholarship]:
        return [self.item]


class FakeDetailFetcher:
    def fetch_with_diagnostics(self, scholarship: Scholarship) -> DetailFetchResult:
        body = (
            "申請對象為大專校院電子工程相關科系在校生，"
            "學業平均八十分以上。"
        )
        source = ResourceDiagnostic(
            "source",
            scholarship.source_url,
            scholarship.source_url,
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


class FakeModels:
    def count_tokens(self, **_: object) -> object:
        return SimpleNamespace(total_tokens=150)

    def generate_content(self, **_: object) -> object:
        return SimpleNamespace(
            text=(
                '{"document_type":"scholarship_rules",'
                '"criteria_complete":true,'
                '"needs_more_pages":false,'
                '"applicant_groups":["大專校院在校生"],'
                '"departments_included":["電子工程相關科系"],'
                '"minimum_average_grade":80,'
                '"other_required_conditions":["須由系主任推薦"],'
                '"evidence":[{"page":1,"text":"須由系主任推薦"}]}'
            ),
            usage_metadata=SimpleNamespace(
                prompt_token_count=120,
                candidates_token_count=30,
                total_token_count=150,
            ),
        )


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
        research_keywords=("電力電子", "能源"),
    )


def _gemini(tmp_path: Path) -> GeminiFallbackService:
    extractor = GeminiRequirementExtractor(
        api_key="test-key",
        model="gemini-test",
        max_pages=2,
        max_download_bytes=1024 * 1024,
        max_input_tokens=5000,
        max_output_tokens=500,
        timeout_seconds=5,
        user_agent="test",
    )
    extractor.client = SimpleNamespace(models=FakeModels())
    return GeminiFallbackService(
        extractor,
        GeminiCacheRepository(tmp_path / "gemini.db"),
        GeminiUsageLimiter(max_calls=2, max_input_tokens=5000),
        "prompt-v1",
    )


def test_audit_compares_legacy_and_structured_without_writing_repository(
    tmp_path: Path,
) -> None:
    item = Scholarship.from_raw(
        "lhu",
        "電力與能源工程獎學金",
        "2026-07-27",
        "https://example.com/item",
    )
    repository = ScholarshipRepository(tmp_path / "scholarships.db")
    service = ScholarshipService(
        FakeCollector(item),
        repository,
        lambda _: None,
        include_keywords=("獎學金",),
        summary_batch_size=5,
        detail_fetcher=FakeDetailFetcher(),
        evaluator=EligibilityEvaluator(),
        profile=_profile(),
        gemini_fallback=_gemini(tmp_path),
    )

    result = service.audit()
    record = result.records[0]

    assert result.eligible_count == 1
    assert result.structured_review_count == 1
    assert result.structured_difference_count == 1
    assert record.item.eligibility_status == "eligible"
    assert record.structured_comparison is not None
    assert record.structured_comparison.structured_status == "review"
    assert "系主任推薦" in record.structured_comparison.structured_reason
    assert record.structured_diagnostic is not None
    assert repository.is_empty()
