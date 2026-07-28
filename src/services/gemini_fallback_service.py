# -*- coding: utf-8 -*-

from dataclasses import dataclass
from hashlib import sha256

from config import GEMINI_PARTIAL_EXCLUSION_MARKER
from src.ai.gemini_requirement_extractor import (
    GeminiApiResult,
    GeminiRequirementExtraction,
    GeminiRequirementExtractor,
    PreparedGeminiDocument,
    RequirementEvidence,
)
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.repositories.gemini_cache_repository import GeminiCacheEntry, GeminiCacheRepository


@dataclass(frozen=True)
class GeminiAnalysisDiagnostic:
    """單筆公告的 Gemini 備援處理結果。"""

    status: str
    source_url: str
    model: str
    cache_hit: bool
    selected_pages: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    message: str
    extracted_fields: tuple[str, ...] = tuple()
    evidence: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class GeminiFallbackResult:
    """可交給既有資格規則的文字與診斷。"""

    rule_text: str
    diagnostic: GeminiAnalysisDiagnostic


@dataclass(frozen=True)
class GeminiUsageSummary:
    """本次執行實際使用的 Gemini 次數與 Token。"""

    calls: int
    cache_hits: int
    input_tokens: int
    output_tokens: int


class GeminiUsageLimiter:
    """限制單次程式執行的 Gemini 呼叫數與輸入 Token。"""

    def __init__(self, max_calls: int, max_input_tokens: int) -> None:
        self.max_calls = max_calls
        self.max_input_tokens = max_input_tokens
        self.calls = 0
        self.cache_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def has_capacity(self) -> bool:
        return self.calls < self.max_calls and self.input_tokens < self.max_input_tokens

    def reserve(self, estimated_tokens: int) -> bool:
        if not self.has_capacity():
            return False
        if self.input_tokens + estimated_tokens > self.max_input_tokens:
            return False
        self.calls += 1
        self.input_tokens += estimated_tokens
        return True

    def record_actual(self, estimated_tokens: int, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens - estimated_tokens
        self.output_tokens += output_tokens

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    def summary(self) -> GeminiUsageSummary:
        return GeminiUsageSummary(
            self.calls,
            self.cache_hits,
            max(self.input_tokens, 0),
            max(self.output_tokens, 0),
        )


class GeminiFallbackService:
    """只對掃描型主要資格 PDF 的 review 公告啟用 Gemini。"""

    def __init__(
        self,
        extractor: GeminiRequirementExtractor,
        cache: GeminiCacheRepository,
        limiter: GeminiUsageLimiter,
        prompt_version: str,
    ) -> None:
        self.extractor = extractor
        self.cache = cache
        self.limiter = limiter
        self.prompt_version = prompt_version

    def analyze(self, title: str, fetch_result: DetailFetchResult) -> GeminiFallbackResult | None:
        candidate = _find_scanned_pdf(fetch_result.attachments)
        if candidate is None:
            return None
        try:
            document = self.extractor.prepare_document(candidate.requested_url)
        except Exception as error:
            return self._failure(candidate.requested_url, 0, error)
        cache_key = _cache_key(
            document.document_hash,
            self.extractor.model,
            self.prompt_version,
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            return self._cached_result(cached, document.selected_pages)
        if not self.limiter.has_capacity():
            return self._budget_skipped(document)
        return self._call_gemini(title, cache_key, document)

    def usage_summary(self) -> GeminiUsageSummary:
        return self.limiter.summary()

    def _call_gemini(
        self,
        title: str,
        cache_key: str,
        document: PreparedGeminiDocument,
    ) -> GeminiFallbackResult:
        if not self.limiter.has_capacity():
            return self._budget_skipped(document)
        try:
            estimated = self.extractor.count_tokens(title, document)
        except Exception as error:
            return self._failure(document.requested_url, document.selected_pages, error)
        if not self.limiter.reserve(estimated):
            return self._budget_skipped(document)
        try:
            api_result = self.extractor.extract(title, document)
        except Exception as error:
            self._save_error(cache_key, document, estimated, error)
            return self._failure(document.requested_url, document.selected_pages, error)
        self.limiter.record_actual(
            estimated,
            api_result.input_tokens,
            api_result.output_tokens,
        )
        self._save_success(cache_key, document, api_result)
        return self._extraction_result(api_result.extraction, document, api_result)

    def _cached_result(
        self,
        entry: GeminiCacheEntry,
        selected_pages: int,
    ) -> GeminiFallbackResult:
        self.limiter.record_cache_hit()
        if entry.status != "success":
            diagnostic = GeminiAnalysisDiagnostic(
                "cached_error",
                entry.source_url,
                entry.model,
                True,
                selected_pages,
                0,
                0,
                0,
                entry.error or "先前 Gemini 解析失敗，使用錯誤快取。",
            )
            return GeminiFallbackResult("", diagnostic)
        extraction = GeminiRequirementExtraction.model_validate_json(entry.extracted_json)
        diagnostic = _usable_diagnostic(
            extraction,
            entry.source_url,
            entry.model,
            True,
            selected_pages,
            0,
            0,
            0,
        )
        return GeminiFallbackResult(_usable_rule_text(extraction), diagnostic)

    def _extraction_result(
        self,
        extraction: GeminiRequirementExtraction,
        document: PreparedGeminiDocument,
        api_result: GeminiApiResult,
    ) -> GeminiFallbackResult:
        diagnostic = _usable_diagnostic(
            extraction,
            document.final_url,
            self.extractor.model,
            False,
            document.selected_pages,
            api_result.input_tokens,
            api_result.output_tokens,
            api_result.total_tokens,
        )
        return GeminiFallbackResult(_usable_rule_text(extraction), diagnostic)

    def _save_success(
        self,
        cache_key: str,
        document: PreparedGeminiDocument,
        api_result: GeminiApiResult,
    ) -> None:
        entry = GeminiCacheEntry(
            cache_key,
            document.document_hash,
            document.final_url,
            self.extractor.model,
            self.prompt_version,
            "success",
            api_result.extraction.model_dump_json(),
            api_result.input_tokens,
            api_result.output_tokens,
            api_result.total_tokens,
            "",
        )
        self.cache.save(entry)

    def _save_error(
        self,
        cache_key: str,
        document: PreparedGeminiDocument,
        tokens: int,
        error: Exception,
    ) -> None:
        entry = GeminiCacheEntry(
            cache_key,
            document.document_hash,
            document.final_url,
            self.extractor.model,
            self.prompt_version,
            "error",
            "",
            tokens,
            0,
            tokens,
            _error_text(error),
        )
        self.cache.save(entry)

    def _failure(self, url: str, pages: int, error: Exception) -> GeminiFallbackResult:
        diagnostic = GeminiAnalysisDiagnostic(
            "error",
            url,
            self.extractor.model,
            False,
            pages,
            0,
            0,
            0,
            _error_text(error),
        )
        return GeminiFallbackResult("", diagnostic)

    def _budget_skipped(self, document: PreparedGeminiDocument) -> GeminiFallbackResult:
        message = "已達本次 Gemini 呼叫或輸入 Token 上限，維持 review。"
        return self._diagnostic_result("budget_skipped", document, 0, 0, 0, message)

    def _diagnostic_result(
        self,
        status: str,
        document: PreparedGeminiDocument,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        message: str,
    ) -> GeminiFallbackResult:
        diagnostic = GeminiAnalysisDiagnostic(
            status,
            document.final_url,
            self.extractor.model,
            False,
            document.selected_pages,
            input_tokens,
            output_tokens,
            total_tokens,
            message,
        )
        return GeminiFallbackResult("", diagnostic)


def _find_scanned_pdf(items: tuple[ResourceDiagnostic, ...]) -> ResourceDiagnostic | None:
    scanned = [item for item in items if _is_scanned_pdf(item)]
    for role in ("rules", "unknown", "unrelated"):
        candidate = next((item for item in scanned if item.attachment_role == role), None)
        if candidate is not None:
            return candidate
    return None


def _is_scanned_pdf(item: ResourceDiagnostic) -> bool:
    scanned = "沒有可擷取文字" in item.error or "掃描檔" in item.error
    return item.status == "error" and item.document_kind == "pdf" and scanned


def _cache_key(document_hash: str, model: str, prompt_version: str) -> str:
    payload = f"{document_hash}:{model}:{prompt_version}".encode("utf-8")
    return sha256(payload).hexdigest()


def _usable_rule_text(extraction: GeminiRequirementExtraction) -> str:
    complete = _complete_rule_text(extraction)
    if complete:
        return complete
    return _partial_exclusion_rule_text(extraction)


def _complete_rule_text(extraction: GeminiRequirementExtraction) -> str:
    if extraction.document_type != "scholarship_rules":
        return ""
    if not extraction.criteria_complete or extraction.needs_more_pages:
        return ""
    if not extraction.evidence:
        return ""
    return extraction.to_rule_text()


def _partial_exclusion_rule_text(extraction: GeminiRequirementExtraction) -> str:
    if extraction.document_type not in ("scholarship_rules", "other"):
        return ""
    if not extraction.evidence:
        return ""
    rules: list[str] = []
    for value in extraction.required_special_statuses:
        if _evidence_supports(value, extraction.evidence):
            rules.append(f"申請資格限於{value}")
    for value in extraction.program_types_excluded:
        if _evidence_supports(value, extraction.evidence):
            rules.append(f"不包括{value}")
    for value in extraction.departments_excluded:
        if _evidence_supports(value, extraction.evidence):
            rules.append(f"不包括相關科系：{value}")
    for value in extraction.explicit_exclusions:
        if _evidence_supports(value, extraction.evidence):
            rules.append(f"不包括{value}")
    if not rules:
        return ""
    body = "。".join(dict.fromkeys(rules)) + "。"
    return f"{GEMINI_PARTIAL_EXCLUSION_MARKER}{body}"


def _evidence_supports(value: str, evidence: list[RequirementEvidence]) -> bool:
    target = "".join(value.split()).strip("。；;，,：:")
    if not target:
        return False
    return any(target in "".join(item.text.split()) for item in evidence)


def _usable_diagnostic(
    extraction: GeminiRequirementExtraction,
    source_url: str,
    model: str,
    cache_hit: bool,
    pages: int,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
) -> GeminiAnalysisDiagnostic:
    complete = bool(_complete_rule_text(extraction))
    partial = bool(_partial_exclusion_rule_text(extraction))
    if complete:
        status = "cache" if cache_hit else "success"
        message = "已抽取完整資格條件。"
    elif partial:
        status = "cache_partial_exclusion" if cache_hit else "partial_exclusion"
        message = "條件尚未完整，但已取得有頁碼證據的硬性排除條件。"
    else:
        status = "incomplete"
        message = "提供頁面不足或文件不是完整申請辦法。"
    return GeminiAnalysisDiagnostic(
        status,
        source_url,
        model,
        cache_hit,
        pages,
        input_tokens,
        output_tokens,
        total_tokens,
        message,
        _extracted_fields(extraction),
        tuple(f"第{item.page}頁：{item.text}" for item in extraction.evidence),
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
