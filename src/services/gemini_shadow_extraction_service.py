# -*- coding: utf-8 -*-

from dataclasses import dataclass
from hashlib import sha256
import json

from src.ai.gemini_requirement_extractor import (
    GeminiApiResult,
    GeminiRequirementExtraction,
    RequirementEvidence,
)
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.repositories.gemini_cache_repository import GeminiCacheEntry
from src.services.gemini_fallback_service import (
    GeminiAnalysisDiagnostic,
    GeminiFallbackService,
)

TEXT_SHADOW_PROMPT_VERSION = "text-shadow-v1"


@dataclass(frozen=True)
class GeminiShadowResult:
    """文字抽取的結構化結果與診斷，不改變正式資格狀態。"""

    extraction: GeminiRequirementExtraction | None
    diagnostic: GeminiAnalysisDiagnostic


def analyze_text_shadow(
    fallback: GeminiFallbackService,
    title: str,
    fetch_result: DetailFetchResult,
) -> GeminiShadowResult | None:
    """對公告正文與已解析附件執行 shadow 抽取。"""
    body_text = (fetch_result.body_text or fetch_result.text).strip()
    attachment_texts = _attachment_inputs(fetch_result)
    if not body_text and not attachment_texts:
        return None

    source_url = fetch_result.source.final_url or fetch_result.source.requested_url
    document_hash = _text_document_hash(title, body_text, attachment_texts)
    prompt_version = f"{fallback.prompt_version}:{TEXT_SHADOW_PROMPT_VERSION}"
    cache_key = _cache_key(document_hash, fallback.extractor.model, prompt_version)
    cached = fallback.cache.get(cache_key)
    if cached is not None:
        fallback.limiter.record_cache_hit()
        return _cached_result(cached)

    if not fallback.limiter.has_capacity():
        return _diagnostic_only(
            fallback,
            source_url,
            "budget_skipped",
            "已達本次 Gemini 呼叫或輸入 Token 上限，shadow 維持未判斷。",
        )

    try:
        estimated = fallback.extractor.count_text_tokens(
            title,
            body_text,
            attachment_texts,
        )
    except Exception as error:
        return _error_result(fallback, source_url, error)
    if not fallback.limiter.reserve(estimated):
        return _diagnostic_only(
            fallback,
            source_url,
            "budget_skipped",
            "已達本次 Gemini 呼叫或輸入 Token 上限，shadow 維持未判斷。",
        )

    try:
        api_result = fallback.extractor.extract_from_text(
            title,
            body_text,
            attachment_texts,
        )
    except Exception as error:
        _save_error(
            fallback,
            cache_key,
            document_hash,
            source_url,
            prompt_version,
            estimated,
            error,
        )
        return _error_result(fallback, source_url, error)

    fallback.limiter.record_actual(
        estimated,
        api_result.input_tokens,
        api_result.output_tokens,
    )
    _save_success(
        fallback,
        cache_key,
        document_hash,
        source_url,
        prompt_version,
        api_result,
    )
    return GeminiShadowResult(
        api_result.extraction,
        _diagnostic(
            api_result.extraction,
            source_url,
            fallback.extractor.model,
            False,
            api_result.input_tokens,
            api_result.output_tokens,
            api_result.total_tokens,
        ),
    )


def _attachment_inputs(fetch_result: DetailFetchResult) -> list[str]:
    inputs: list[str] = []
    for item in fetch_result.extracted_attachments:
        if item.status != "success" or not item.text.strip():
            continue
        header = (
            f"標籤={item.label or '未命名'}；"
            f"角色提示={item.role_hint}；內容角色={item.content_role}"
        )
        inputs.append(f"【{header}】\n{item.text.strip()}")
    return inputs


def _text_document_hash(title: str, body_text: str, attachments: list[str]) -> str:
    payload = json.dumps(
        {
            "title": title,
            "body": body_text,
            "attachments": attachments,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _cache_key(document_hash: str, model: str, prompt_version: str) -> str:
    payload = f"{document_hash}:{model}:{prompt_version}".encode("utf-8")
    return sha256(payload).hexdigest()


def _cached_result(entry: GeminiCacheEntry) -> GeminiShadowResult:
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
        return GeminiShadowResult(None, diagnostic)
    extraction = GeminiRequirementExtraction.model_validate_json(entry.extracted_json)
    return GeminiShadowResult(
        extraction,
        _diagnostic(extraction, entry.source_url, entry.model, True, 0, 0, 0),
    )


def _save_success(
    fallback: GeminiFallbackService,
    cache_key: str,
    document_hash: str,
    source_url: str,
    prompt_version: str,
    api_result: GeminiApiResult,
) -> None:
    fallback.cache.save(
        GeminiCacheEntry(
            cache_key,
            document_hash,
            source_url,
            fallback.extractor.model,
            prompt_version,
            "success",
            api_result.extraction.model_dump_json(),
            api_result.input_tokens,
            api_result.output_tokens,
            api_result.total_tokens,
            "",
        )
    )


def _save_error(
    fallback: GeminiFallbackService,
    cache_key: str,
    document_hash: str,
    source_url: str,
    prompt_version: str,
    estimated: int,
    error: Exception,
) -> None:
    fallback.cache.save(
        GeminiCacheEntry(
            cache_key,
            document_hash,
            source_url,
            fallback.extractor.model,
            prompt_version,
            "error",
            "",
            estimated,
            0,
            estimated,
            _error_text(error),
        )
    )


def _error_result(
    fallback: GeminiFallbackService,
    source_url: str,
    error: Exception,
) -> GeminiShadowResult:
    return GeminiShadowResult(
        None,
        GeminiAnalysisDiagnostic(
            "error",
            source_url,
            fallback.extractor.model,
            False,
            0,
            0,
            0,
            0,
            _error_text(error),
        ),
    )


def _diagnostic_only(
    fallback: GeminiFallbackService,
    source_url: str,
    status: str,
    message: str,
) -> GeminiShadowResult:
    return GeminiShadowResult(
        None,
        GeminiAnalysisDiagnostic(
            status,
            source_url,
            fallback.extractor.model,
            False,
            0,
            0,
            0,
            0,
            message,
        ),
    )


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
    status = "shadow_cache" if cache_hit else "shadow_success"
    message = "shadow 已抽取完整資格條件。" if complete else "shadow 抽取完成，但資格仍不完整。"
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
        tuple(_format_evidence(item) for item in extraction.evidence),
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


def _format_evidence(item: RequirementEvidence) -> str:
    if item.source_kind == "attachment_pdf":
        location = f"附件PDF第{item.page or '?'}頁"
    elif item.source_kind == "attachment_text":
        location = f"附件文字{item.source_index or '?'}"
    elif item.source_kind == "body":
        location = "公告正文"
    else:
        location = "公告標題"
    return f"{location}：{item.text}"


def _error_text(error: Exception) -> str:
    return f"{type(error).__name__}: {' '.join(str(error).split())}"[:240]
