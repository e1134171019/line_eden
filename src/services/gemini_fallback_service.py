# -*- coding: utf-8 -*-

from dataclasses import dataclass
from hashlib import sha256

from src.ai.gemini_requirement_extractor import (
    GeminiRequirementExtraction,
    GeminiRequirementExtractor,
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

    # 在生成前預留一次呼叫與估算輸入 Token。
    def reserve(self, estimated_tokens: int) -> bool:
        if self.calls >= self.max_calls:
            return False
        if self.input_tokens + estimated_tokens > self.max_input_tokens:
            return False
        self.calls += 1
        self.input_tokens += estimated_tokens
        return True

    # 以 API 回傳的實際 Token 修正預估值並記錄輸出。
    def record_actual(self, estimated_tokens: int, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens - estimated_tokens
        self.output_tokens += output_tokens

    # 記錄本次直接使用既有文件快取。
    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    # 建立可顯示於 dry-run 與 audit 的使用摘要。
    def summary(self) -> GeminiUsageSummary:
        return GeminiUsageSummary(
            self.calls,
            self.cache_hits,
            max(self.input_tokens, 0),
            max(self.output_tokens, 0),
        )


class GeminiFallbackService:
    """只對掃描型 PDF 的 review 公告啟用 Gemini。"""

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

    # 從附件診斷挑選第一個掃描型 PDF，其他情況完全不呼叫 Gemini。
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
        return self._call_gemini(title, cache_key, document)

    # 回傳本次執行的呼叫、快取與 Token 統計。
    def usage_summary(self) -> GeminiUsageSummary:
        return self.limiter.summary()

    # Token 計數通過預算後才真正呼叫生成 API。
    def _call_gemini(self, title: str, cache_key: str, document: object) -> GeminiFallbackResult:
        try:
            estimated = self.extractor.count_tokens(title, document)
        except Exception as error:
            return self._failure(document.requested_url, document.selected_pages, error)
        if not self.limiter.reserve(estimated):
            message = "已達本次 Gemini 呼叫或輸入 Token 上限，維持 review。"
            return self._diagnostic_result("budget_skipped", document, 0, 0, 0, message)
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

    # 將成功快取還原成結構化結果，不產生本次 Token。
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

    # 建立本次 API 成功但可能仍不足的結果。
    def _extraction_result(self, extraction: object, document: object, api_result: object) -> GeminiFallbackResult:
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

    # 保存模型回傳 JSON 與實際 Token，快取內容不含 profile.json。
    def _save_success(self, cache_key: str, document: object, api_result: object) -> None:
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

    # 保存已消耗呼叫但失敗的結果，避免每次執行重複花費。
    def _save_error(self, cache_key: str, document: object, tokens: int, error: Exception) -> None:
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

    # 建立下載、計數或 API 失敗診斷，不改變原本 review 決策。
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

    # 建立預算跳過等不含資格文字的診斷。
    def _diagnostic_result(
        self,
        status: str,
        document: object,
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


# 只挑選已下載成功但沒有文字層的 PDF 附件。
def _find_scanned_pdf(items: tuple[ResourceDiagnostic, ...]) -> ResourceDiagnostic | None:
    for item in items:
        scanned = "沒有可擷取文字" in item.error or "掃描檔" in item.error
        if item.status == "error" and item.document_kind == "pdf" and scanned:
            return item
    return None


# 文件內容、模型與提示版本共同決定永久快取鍵。
def _cache_key(document_hash: str, model: str, prompt_version: str) -> str:
    payload = f"{document_hash}:{model}:{prompt_version}".encode("utf-8")
    return sha256(payload).hexdigest()


# 只有完整辦法、無需更多頁且具有證據時才產生規則文字。
def _usable_rule_text(extraction: GeminiRequirementExtraction) -> str:
    if extraction.document_type != "scholarship_rules":
        return ""
    if not extraction.criteria_complete or extraction.needs_more_pages:
        return ""
    if not extraction.evidence:
        return ""
    return extraction.to_rule_text()


# 依結構化內容完整度建立成功或不足診斷。
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
    usable = bool(_usable_rule_text(extraction))
    status = "cache" if cache_hit and usable else "success" if usable else "incomplete"
    message = "已抽取完整資格條件。" if usable else "提供頁面不足或文件不是完整申請辦法。"
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
    )


# 將外部例外整理成有限長度的單行訊息。
def _error_text(error: Exception) -> str:
    return f"{type(error).__name__}: {' '.join(str(error).split())}"[:240]
