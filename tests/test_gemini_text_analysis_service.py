# -*- coding: utf-8 -*-

from pathlib import Path
from types import SimpleNamespace

from src.ai.gemini_requirement_extractor import (
    GeminiApiResult,
    GeminiRequirementExtraction,
    RequirementEvidence,
)
from src.ai.gemini_text_requirement_extractor import PreparedGeminiText
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.repositories.gemini_cache_repository import GeminiCacheRepository
from src.services.gemini_fallback_service import GeminiUsageLimiter
from src.services.gemini_text_analysis_service import GeminiTextAnalysisService


class FakeTextExtractor:
    def __init__(self) -> None:
        self.extractor = SimpleNamespace(model="test-model")
        self.calls = 0

    def prepare(self, _: str, __: DetailFetchResult) -> PreparedGeminiText:
        return PreparedGeminiText("a" * 64, "測試 prompt")

    def count_tokens(self, _: PreparedGeminiText) -> int:
        return 100

    def extract(self, _: PreparedGeminiText) -> GeminiApiResult:
        self.calls += 1
        extraction = GeminiRequirementExtraction(
            document_type="scholarship_rules",
            criteria_complete=True,
            needs_more_pages=False,
            degree_levels=["大學生"],
            evidence=[RequirementEvidence(page=1, text="大學生可申請")],
        )
        return GeminiApiResult(extraction, 100, 20, 120)


def _fetch_result() -> DetailFetchResult:
    source = ResourceDiagnostic(
        "source",
        "https://example.com/item",
        "https://example.com/item",
        "text/html",
        20,
        "html",
        "success",
        10,
    )
    return DetailFetchResult("正文", source, tuple(), 0, body_text="正文")


def test_text_analysis_uses_persistent_cache(tmp_path: Path) -> None:
    extractor = FakeTextExtractor()
    cache = GeminiCacheRepository(tmp_path / "gemini.db")
    first = GeminiTextAnalysisService(
        extractor,
        cache,
        GeminiUsageLimiter(3, 12000),
        "text-v1",
    )

    first_result = first.analyze("獎學金", _fetch_result())

    assert first_result.extraction is not None
    assert first_result.diagnostic.status == "text_success"
    assert extractor.calls == 1

    second = GeminiTextAnalysisService(
        extractor,
        cache,
        GeminiUsageLimiter(3, 12000),
        "text-v1",
    )
    second_result = second.analyze("獎學金", _fetch_result())

    assert second_result.extraction is not None
    assert second_result.diagnostic.status == "text_cache"
    assert second_result.diagnostic.cache_hit is True
    assert extractor.calls == 1


def test_text_analysis_defers_without_writing_error_cache(tmp_path: Path) -> None:
    extractor = FakeTextExtractor()
    cache = GeminiCacheRepository(tmp_path / "gemini.db")
    service = GeminiTextAnalysisService(
        extractor,
        cache,
        GeminiUsageLimiter(0, 0),
        "text-v1",
    )

    result = service.analyze("獎學金", _fetch_result())

    assert result.extraction is None
    assert result.diagnostic.status == "budget_deferred"
    assert extractor.calls == 0
