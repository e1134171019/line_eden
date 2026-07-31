# -*- coding: utf-8 -*-

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from src.ai.gemini_requirement_extractor import (
    GeminiApiResult,
    GeminiRequirementExtraction,
    RequirementEvidence,
)
from src.ai.gemini_text_requirement_extractor import PreparedGeminiText
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.repositories.gemini_cache_repository import GeminiCacheEntry, GeminiCacheRepository
from src.services.gemini_fallback_service import GeminiUsageLimiter
from src.services.gemini_text_analysis_service import GeminiTextAnalysisService


class FakeTextExtractor:
    def __init__(self) -> None:
        self.extractor = SimpleNamespace(model="test-model")
        self.prepare_calls = 0
        self.calls = 0

    def prepare(self, _: str, __: DetailFetchResult) -> PreparedGeminiText:
        self.prepare_calls += 1
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


def _fetch_result(body: str = "正文") -> DetailFetchResult:
    source = ResourceDiagnostic(
        "source",
        "https://example.com/item",
        "https://example.com/item",
        "text/html",
        len(body.encode("utf-8")),
        "html",
        "success",
        len(body),
    )
    return DetailFetchResult(body, source, tuple(), 0, body_text=body)


def _cache_key(prompt_version: str) -> str:
    payload = f"text:{'a' * 64}:test-model:{prompt_version}".encode("utf-8")
    return sha256(payload).hexdigest()


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


def test_text_analysis_retries_previously_cached_error(tmp_path: Path) -> None:
    extractor = FakeTextExtractor()
    cache = GeminiCacheRepository(tmp_path / "gemini.db")
    prompt_version = "text-v1"
    key = _cache_key(prompt_version)
    cache.save(
        GeminiCacheEntry(
            key,
            "a" * 64,
            "https://example.com/item",
            "test-model",
            prompt_version,
            "error",
            "",
            100,
            0,
            100,
            "RuntimeError: temporary failure",
        )
    )
    service = GeminiTextAnalysisService(
        extractor,
        cache,
        GeminiUsageLimiter(3, 12000),
        prompt_version,
    )

    result = service.analyze("獎學金", _fetch_result())

    assert result.extraction is not None
    assert result.diagnostic.status == "text_success"
    assert extractor.calls == 1
    assert cache.get(key) is not None
    assert cache.get(key).status == "success"  # type: ignore[union-attr]


def test_text_analysis_skips_expired_notice_before_preparing_prompt(tmp_path: Path) -> None:
    extractor = FakeTextExtractor()
    service = GeminiTextAnalysisService(
        extractor,
        GeminiCacheRepository(tmp_path / "gemini.db"),
        GeminiUsageLimiter(3, 12000),
        "text-v1",
    )
    expired = _fetch_result("申請截止日期為109年9月30日。")

    result = service.analyze("109年留學獎學金甄試簡章", expired)

    assert result.extraction is None
    assert result.diagnostic.status == "expired"
    assert extractor.prepare_calls == 0
    assert extractor.calls == 0
