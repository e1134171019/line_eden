# -*- coding: utf-8 -*-

from dataclasses import dataclass
from hashlib import sha256

from config import GEMINI_MAX_ATTEMPTS, GEMINI_RETRY_BASE_SECONDS
from src.ai.gemini_requirement_extractor import (
    GeminiApiResult,
    GeminiRequirementExtraction,
)
from src.ai.gemini_retry import run_with_retry
from src.ai.gemini_text_requirement_extractor import (
    GeminiTextRequirementExtractor,
    PreparedGeminiText,
)
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.repositories.gemini_cache_repository import GeminiCacheEntry, GeminiCacheRepository
from src.services.gemini_fallback_service import (
    GeminiAnalysisDiagnostic,
    GeminiUsageLimiter,
    _error_text,
    _extracted_fields,
)
from src.services.structured_shadow_scope import structured_shadow_skip_status


@dataclass(frozen=True)
class GeminiTextAnalysisResult:
    """文字證據抽取結果；預算延後時 extraction 為 None。"""

    extraction: GeminiRequirementExtraction | None
    diagnostic: GeminiAnalysisDiagnostic


class GeminiTextAnalysisService:
    """使用正文與已解析附件執行可快取、受預算限制的 Gemini 抽取。"""

    def __init__(
        self,
        extractor: GeminiTextRequirementExtractor,
        cache: GeminiCacheRepository,
        limiter: GeminiUsageLimiter,
        prompt_version: str,
    ) -> None:
        self.extractor = extractor
        self.cache = cache
        self.limiter = limiter
        self.prompt_version = prompt_version

    def analyze(self, title: str, fetch_result: DetailFetchResult) -> GeminiTextAnalysisResult:
        model = self.extractor.extractor.model
        source_url = fetch_result.source.final_url or fetch_result.source.requested_url
        skip_status = structured_shadow_skip_status(title, fetch_result)
        if skip_status is not None:
            return self._skipped(source_url, model, skip_status)

        prepared = self.extractor.prepare(title, fetch_result)
        cache_key = _cache_key(prepared.content_hash, model, self.prompt_version)
        cached = self.cache.get(cache_key)
        if cached is not None and cached.status == "success":
            return self._cached_result(cached)
        if cached is not None:
            self.cache.delete(cache_key)
        if not self.limiter.has_capacity():
            return self._deferred(source_url, model)
        try:
            estimated = self._count_tokens(prepared)
        except Exception as error:
            return self._failure(source_url, model, error)
        if not self.limiter.reserve(estimated):
            return self._deferred(source_url, model)
        try:
            api_result = self._extract(prepared)
        except Exception as error:
            return self._failure(source_url, model, error)
        self.limiter.record_actual(
            estimated,
            api_result.input_tokens,
            api_result.output_tokens,
        )
        self._save_success(cache_key, prepared.content_hash, source_url, model, api_result)
        diagnostic = _diagnostic(
            api_result.extraction,
            source_url,
            model,
            False,
            api_result.input_tokens,
            api_result.output_tokens,
            api_result.total_tokens,
        )
        return GeminiTextAnalysisResult(api_result.extraction, diagnostic)

    # count_tokens 也可能遇到 429、逾時或服務端錯誤，套用相同重試策略。
    def _count_tokens(self, prepared: PreparedGeminiText) -> int:
        return run_with_retry(
            lambda: self.extractor.count_tokens(prepared),
            GEMINI_MAX_ATTEMPTS,
            GEMINI_RETRY_BASE_SECONDS,
        )

    # 生成只對可恢復錯誤重試；Schema 或內容錯誤立即回報。
    def _extract(self, prepared: PreparedGeminiText) -> GeminiApiResult:
        return run_with_retry(
            lambda: self.extractor.extract(prepared),
            GEMINI_MAX_ATTEMPTS,
            GEMINI_RETRY_BASE_SECONDS,
        )

    def _cached_result(self, entry: GeminiCacheEntry) -> GeminiTextAnalysisResult:
        self.limiter.record_cache_hit()
        extraction = GeminiRequirementExtraction.model_validate_json(entry.extracted_json)
        diagnostic = _diagnostic(extraction, entry.source_url, entry.model, True, 0, 0, 0)
        return GeminiTextAnalysisResult(extraction, diagnostic)

    def _save_success(
        self,
        cache_key: str,
        content_hash: str,
        source_url: str,
        model: str,
        api_result: GeminiApiResult,
    ) -> None:
        self.cache.save(
            GeminiCacheEntry(
                cache_key,
                content_hash,
                source_url,
                model,
                self.prompt_version,
                "success",
                api_result.extraction.model_dump_json(),
                api_result.input_tokens,
                api_result.output_tokens,
                api_result.total_tokens,
                "",
            )
        )

    def _skipped(
        self,
        source_url: str,
        model: str,
        status: str,
    ) -> GeminiTextAnalysisResult:
        diagnostic = GeminiAnalysisDiagnostic(
            status,
            source_url,
            model,
            False,
            0,
            0,
            0,
            0,
            "申請期限已截止，不執行 structured shadow。",
        )
        return GeminiTextAnalysisResult(None, diagnostic)

    def _deferred(self, source_url: str, model: str) -> GeminiTextAnalysisResult:
        diagnostic = GeminiAnalysisDiagnostic(
            "budget_deferred",
            source_url,
            model,
            False,
            0,
            0,
            0,
            0,
            "已達本次 Gemini 呼叫或 Token 上限，保留至下一次 audit。",
        )
        return GeminiTextAnalysisResult(None, diagnostic)

    def _failure(
        self,
        source_url: str,
        model: str,
        error: Exception,
    ) -> GeminiTextAnalysisResult:
        diagnostic = GeminiAnalysisDiagnostic(
            "text_error",
            source_url,
            model,
            False,
            0,
            0,
            0,
            0,
            _error_text(error),
        )
        return GeminiTextAnalysisResult(None, diagnostic)


def _cache_key(content_hash: str, model: str, prompt_version: str) -> str:
    payload = f"text:{content_hash}:{model}:{prompt_version}".encode("utf-8")
    return sha256(payload).hexdigest()


def _diagnostic(
    extraction: GeminiRequirementExtraction,
    source_url: str,
    model: str,
    cache_hit: bool,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
) -> GeminiAnalysisDiagnostic:
    complete = (
        extraction.document_type == "scholarship_rules"
        and extraction.criteria_complete
        and not extraction.needs_more_pages
        and bool(extraction.evidence)
    )
    status = "text_cache" if cache_hit else "text_success"
    if not complete:
        status = "text_cache_incomplete" if cache_hit else "text_incomplete"
    message = "已完成文字資格抽取。" if complete else "文字資格抽取完成，但條件或證據仍不完整。"
    return GeminiAnalysisDiagnostic(
        status,
        source_url,
        model,
        cache_hit,
        0,
        input_tokens,
        output_tokens,
        total_tokens,
        message,
        _extracted_fields(extraction),
        tuple(f"文字證據：{item.text}" for item in extraction.evidence),
    )
