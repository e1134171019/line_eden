# -*- coding: utf-8 -*-

from dataclasses import dataclass
from hashlib import sha256

from src.ai.gemini_requirement_extractor import (
    GeminiApiResult,
    GeminiRequirementExtraction,
)
from src.ai.gemini_text_requirement_extractor import GeminiTextRequirementExtractor
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.repositories.gemini_cache_repository import GeminiCacheEntry
from src.services.gemini_fallback_service import (
    GeminiAnalysisDiagnostic,
    GeminiFallbackService,
)

TEXT_SHADOW_VERSION = "text-shadow-v1"


@dataclass(frozen=True)
class GeminiTextShadowResult:
    """文字抽取結果與診斷；只供 audit shadow，不改正式狀態。"""

    extraction: GeminiRequirementExtraction | None
    diagnostic: GeminiAnalysisDiagnostic


class GeminiTextShadowService:
    """共用既有 Gemini 快取與預算，執行正文／附件文字抽取。"""

    def __init__(self, fallback: GeminiFallbackService) -> None:
        self.fallback = fallback
        self.extractor = GeminiTextRequirementExtractor(fallback.extractor)
        self.prompt_version = f"{fallback.prompt_version}:{TEXT_SHADOW_VERSION}"

    def analyze(
        self,
        title: str,
        fetch_result: DetailFetchResult,
    ) -> GeminiTextShadowResult | None:
        prepared = self.extractor.prepare(title, fetch_result)
        if not prepared.prompt.strip():
            return None
        cache_key = _cache_key(
            prepared.content_hash,
            self.fallback.extractor.model,
            self.prompt_version,
        )
        cached = self.fallback.cache.get(cache_key)
        if cached is not None:
            self.fallback.limiter.record_cache_hit()
            return self._cached_result(cached)
        source_url = fetch_result.source.final_url or fetch_result.source.requested_url
        if not self.fallback.limiter.has_capacity():
            return self._diagnostic_only(
                source_url,
                "budget_skipped",
                "已達本次 Gemini 呼叫或輸入 Token 上限，structured shadow 尚未執行。",
            )
        try:
            estimated = self.extractor.count_tokens(prepared)
        except Exception as error:
            return self._error_result(source_url, error)
        if not self.fallback.limiter.reserve(estimated):
            return self._diagnostic_only(
                source_url,
                "budget_skipped",
                "已達本次 Gemini 呼叫或輸入 Token 上限，structured shadow 尚未執行。",
            )
        try:
            api_result = self.extractor.extract(prepared)
        except Exception as error:
            self._save_error(
                cache_key,
                prepared.content_hash,
                source_url,
                estimated,
                error,
            )
            return self._error_result(source_url, error)
        self.fallback.limiter.record_actual(
            estimated,
            api_result.input_tokens,
            api_result.output_tokens,
        )
        self._save_success(
            cache_key,
            prepared.content_hash,
            source_url,
            api_result,
        )
        return GeminiTextShadowResult(
            api_result.extraction,
            _build_diagnostic(
                api_result.extraction,
                source_url,
                self.fallback.extractor.model,
                False,
                api_result.input_tokens,
                api_result.output_tokens,
                api_result.total_tokens,
            ),
        )

    def _cached_result(self, entry: GeminiCacheEntry) -> GeminiTextShadowResult:
        if entry.status != "success":
            diagnostic = GeminiAnalysisDiagnostic(
                "cached_error",
                entry.source_url,
                entry.model,
                True,
                0,
                0,
                0,
                0,
                entry.error or "先前 Gemini 文字抽取失敗，使用錯誤快取。",
            )
            return GeminiTextShadowResult(None, diagnostic)
        extraction = GeminiRequirementExtraction.model_validate_json(entry.extracted_json)
        return GeminiTextShadowResult(
            extraction,
            _build_diagnostic(extraction, entry.source_url, entry.model, True, 0, 0, 0),
        )

    def _save_success(
        self,
        cache_key: str,
        content_hash: str,
        source_url: str,
        result: GeminiApiResult,
    ) -> None:
        self.fallback.cache.save(
            GeminiCacheEntry(
                cache_key,
                content_hash,
                source_url,
                self.fallback.extractor.model,
                self.prompt_version,
                "success",
                result.extraction.model_dump_json(),
                result.input_tokens,
                result.output_tokens,
                result.total_tokens,
                "",
            )
        )

    def _save_error(
        self,
        cache_key: str,
        content_hash: str,
        source_url: str,
        estimated: int,
        error: Exception,
    ) -> None:
        self.fallback.cache.save(
            GeminiCacheEntry(
                cache_key,
                content_hash,
                source_url,
                self.fallback.extractor.model,
                self.prompt_version,
                "error",
                "",
                estimated,
                0,
                estimated,
                _error_text(error),
            )
        )

    def _error_result(
        self,
        source_url: str,
        error: Exception,
    ) -> GeminiTextShadowResult:
        return GeminiTextShadowResult(
            None,
            GeminiAnalysisDiagnostic(
                "error",
                source_url,
                self.fallback.extractor.model,
                False,
                0,
                0,
                0,
                0,
                _error_text(error),
            ),
        )

    def _diagnostic_only(
        self,
        source_url: str,
        status: str,
        message: str,
    ) -> GeminiTextShadowResult:
        return GeminiTextShadowResult(
            None,
            GeminiAnalysisDiagnostic(
                status,
                source_url,
                self.fallback.extractor.model,
                False,
                0,
                0,
                0,
                0,
                message,
            ),
        )


def _cache_key(content_hash: str, model: str, prompt_version: str) -> str:
    return sha256(f"{content_hash}:{model}:{prompt_version}".encode("utf-8")).hexdigest()


def _build_diagnostic(
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
    status = "shadow_cache" if cache_hit else "shadow_success"
    message = "structured shadow 抽取完整。" if complete else "structured shadow 抽取完成，但資格仍不完整。"
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


def _extracted_fields(extraction: GeminiRequirementExtraction) -> tuple[str, ...]:
    fields = [
        f"文件類型={extraction.document_type}",
        f"條件完整={extraction.criteria_complete}",
        f"需要更多頁={extraction.needs_more_pages}",
    ]
    _append_list(fields, "申請對象", extraction.applicant_groups)
    _append_list(fields, "學位層級", extraction.degree_levels)
    _append_list(fields, "包含學制", extraction.program_types_included)
    _append_list(fields, "排除學制", extraction.program_types_excluded)
    _append_list(fields, "包含科系", extraction.departments_included)
    _append_list(fields, "排除科系", extraction.departments_excluded)
    _append_list(fields, "年級", extraction.year_requirements)
    _append_list(fields, "必要身分", extraction.required_special_statuses)
    _append_list(fields, "明確排除", extraction.explicit_exclusions)
    _append_list(fields, "其他必要條件", extraction.other_required_conditions)
    if extraction.minimum_average_grade is not None:
        fields.append(f"最低學業={extraction.minimum_average_grade:g}")
    if extraction.minimum_conduct_grade is not None:
        fields.append(f"最低操行={extraction.minimum_conduct_grade:g}")
    if extraction.rank_requirement:
        fields.append(f"排名={extraction.rank_requirement}")
    if extraction.residence_requirement:
        fields.append(f"戶籍={extraction.residence_requirement}")
    if extraction.application_deadline:
        fields.append(f"截止日={extraction.application_deadline}")
    return tuple(fields)


def _append_list(fields: list[str], label: str, values: list[str]) -> None:
    cleaned = [value.strip() for value in values if value.strip()]
    if cleaned:
        fields.append(f"{label}={'、'.join(cleaned)}")


def _error_text(error: Exception) -> str:
    return f"{type(error).__name__}: {' '.join(str(error).split())}"[:240]
