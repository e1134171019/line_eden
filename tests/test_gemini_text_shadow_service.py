# -*- coding: utf-8 -*-

from pathlib import Path
from types import SimpleNamespace

from src.ai.gemini_requirement_extractor import GeminiRequirementExtractor
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.repositories.gemini_cache_repository import GeminiCacheRepository
from src.services.gemini_fallback_service import GeminiFallbackService, GeminiUsageLimiter
from src.services.gemini_text_shadow_service import GeminiTextShadowService


class FakeModels:
    def __init__(self) -> None:
        self.count_calls = 0
        self.generate_calls = 0

    def count_tokens(self, **_: object) -> object:
        self.count_calls += 1
        return SimpleNamespace(total_tokens=120)

    def generate_content(self, **_: object) -> object:
        self.generate_calls += 1
        return SimpleNamespace(
            text=(
                '{"document_type":"scholarship_rules",'
                '"criteria_complete":true,'
                '"needs_more_pages":false,'
                '"applicant_groups":["大專校院在校生"],'
                '"departments_included":["電子工程相關科系"],'
                '"minimum_average_grade":80,'
                '"evidence":[{"page":1,"text":"電子工程相關科系可申請"}]}'
            ),
            usage_metadata=SimpleNamespace(
                prompt_token_count=100,
                candidates_token_count=20,
                total_token_count=120,
            ),
        )


def _fallback(
    tmp_path: Path,
    models: FakeModels,
    max_calls: int,
) -> GeminiFallbackService:
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
    extractor.client = SimpleNamespace(models=models)
    return GeminiFallbackService(
        extractor,
        GeminiCacheRepository(tmp_path / "gemini.db"),
        GeminiUsageLimiter(max_calls=max_calls, max_input_tokens=5000),
        "prompt-v1",
    )


def _fetch_result() -> DetailFetchResult:
    source = ResourceDiagnostic(
        "source",
        "https://example.com/item",
        "https://example.com/item",
        "text/html",
        100,
        "html",
        "success",
        80,
    )
    return DetailFetchResult(
        "申請對象為大專校院電子工程相關科系在校生。",
        source,
        tuple(),
        0,
        body_text="申請對象為大專校院電子工程相關科系在校生。",
    )


def test_text_shadow_uses_cache_without_second_generation(tmp_path: Path) -> None:
    models = FakeModels()
    service = GeminiTextShadowService(_fallback(tmp_path, models, max_calls=1))

    first = service.analyze("能源獎學金", _fetch_result())
    second = service.analyze("能源獎學金", _fetch_result())

    assert first is not None and first.extraction is not None
    assert second is not None and second.extraction is not None
    assert first.diagnostic.status == "shadow_success"
    assert second.diagnostic.status == "shadow_cache"
    assert models.generate_calls == 1
    assert service.fallback.usage_summary().calls == 1
    assert service.fallback.usage_summary().cache_hits == 1


def test_text_shadow_budget_exhaustion_is_diagnostic_only(tmp_path: Path) -> None:
    models = FakeModels()
    service = GeminiTextShadowService(_fallback(tmp_path, models, max_calls=0))

    result = service.analyze("能源獎學金", _fetch_result())

    assert result is not None
    assert result.extraction is None
    assert result.diagnostic.status == "budget_skipped"
    assert models.count_calls == 0
    assert models.generate_calls == 0
