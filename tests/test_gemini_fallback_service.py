# -*- coding: utf-8 -*-

from pathlib import Path

from src.ai.gemini_requirement_extractor import (
    GeminiApiResult,
    GeminiRequirementExtraction,
    PreparedGeminiDocument,
    RequirementEvidence,
)
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.repositories.gemini_cache_repository import GeminiCacheRepository
from src.services.gemini_fallback_service import GeminiFallbackService, GeminiUsageLimiter


class FakeGeminiExtractor:
    """不呼叫外部 API 的 Gemini 測試替身。"""

    model = "gemini-test"

    def __init__(self) -> None:
        self.extract_calls = 0

    # 回傳固定文件雜湊與兩頁裁切內容。
    def prepare_document(self, url: str) -> PreparedGeminiDocument:
        return PreparedGeminiDocument(url, url, "hash-123", b"pdf", 2)

    # 回傳固定輸入 Token 預估。
    def count_tokens(self, title: str, document: PreparedGeminiDocument) -> int:
        return 400

    # 回傳具有證據的完整結構化資格。
    def extract(self, title: str, document: PreparedGeminiDocument) -> GeminiApiResult:
        self.extract_calls += 1
        extraction = GeminiRequirementExtraction(
            document_type="scholarship_rules",
            criteria_complete=True,
            needs_more_pages=False,
            applicant_groups=["大專院校在校生"],
            departments_included=["電子工程相關科系"],
            minimum_average_grade=80,
            evidence=[RequirementEvidence(page=1, text="電子工程相關科系，平均八十分以上")],
        )
        return GeminiApiResult(extraction, 410, 90, 500)


# 建立包含掃描型 PDF 失敗診斷的公告擷取結果。
def _scanned_fetch_result() -> DetailFetchResult:
    source = ResourceDiagnostic(
        "source",
        "https://example.com/notice",
        "https://example.com/notice",
        "text/html",
        100,
        "html",
        "success",
        20,
        "",
    )
    attachment = ResourceDiagnostic(
        "attachment",
        "https://example.com/rules.pdf",
        "https://example.com/rules.pdf",
        "application/pdf",
        1000,
        "pdf",
        "error",
        0,
        "ValueError: PDF 沒有可擷取文字，可能是掃描檔",
    )
    return DetailFetchResult("申請資格請參閱附件。", source, (attachment,), 1)


# 建立測試用 Gemini 備援服務。
def _service(tmp_path: Path, extractor: FakeGeminiExtractor, max_calls: int = 3) -> GeminiFallbackService:
    cache = GeminiCacheRepository(tmp_path / "gemini-cache.db")
    limiter = GeminiUsageLimiter(max_calls=max_calls, max_input_tokens=2000)
    return GeminiFallbackService(extractor, cache, limiter, "prompt-v1")


# 驗證第一次呼叫 API，第二次相同文件直接讀 SQLite 快取。
def test_scanned_pdf_uses_gemini_once_then_cache(tmp_path: Path) -> None:
    extractor = FakeGeminiExtractor()
    service = _service(tmp_path, extractor)

    first = service.analyze("能源工程獎學金", _scanned_fetch_result())
    second = service.analyze("能源工程獎學金", _scanned_fetch_result())

    assert first is not None and "學業平均80分以上" in first.rule_text
    assert second is not None and second.diagnostic.cache_hit is True
    assert extractor.extract_calls == 1
    assert service.usage_summary().calls == 1
    assert service.usage_summary().cache_hits == 1


# 驗證沒有掃描型 PDF 時完全不進入 Gemini。
def test_non_scanned_attachment_does_not_use_gemini(tmp_path: Path) -> None:
    extractor = FakeGeminiExtractor()
    service = _service(tmp_path, extractor)
    source = _scanned_fetch_result().source
    result = DetailFetchResult("公告正文", source, tuple(), 0)

    fallback = service.analyze("一般獎學金", result)

    assert fallback is None
    assert extractor.extract_calls == 0
    assert service.usage_summary().calls == 0


# 驗證呼叫預算用完時維持 review 且不呼叫生成 API。
def test_budget_limit_skips_generation(tmp_path: Path) -> None:
    extractor = FakeGeminiExtractor()
    service = _service(tmp_path, extractor, max_calls=0)

    result = service.analyze("能源工程獎學金", _scanned_fetch_result())

    assert result is not None
    assert result.rule_text == ""
    assert result.diagnostic.status == "budget_skipped"
    assert extractor.extract_calls == 0
