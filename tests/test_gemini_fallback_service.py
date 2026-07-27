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
        self.count_calls = 0
        self.extract_calls = 0
        self.prepared_urls: list[str] = []

    # 回傳固定文件雜湊與兩頁裁切內容。
    def prepare_document(self, url: str) -> PreparedGeminiDocument:
        self.prepared_urls.append(url)
        return PreparedGeminiDocument(url, url, f"hash-{url}", b"pdf", 2)

    # 回傳固定輸入 Token 預估。
    def count_tokens(self, title: str, document: PreparedGeminiDocument) -> int:
        self.count_calls += 1
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
def _scanned_fetch_result(role: str = "unknown") -> DetailFetchResult:
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
        role,
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

    first = service.analyze("能源工程獎學金", _scanned_fetch_result("rules"))
    second = service.analyze("能源工程獎學金", _scanned_fetch_result("rules"))

    assert first is not None and "學業平均80分以上" in first.rule_text
    assert first.diagnostic.extracted_fields
    assert first.diagnostic.evidence == ("第1頁：電子工程相關科系，平均八十分以上",)
    assert second is not None and second.diagnostic.cache_hit is True
    assert second.diagnostic.extracted_fields
    assert extractor.count_calls == 1
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
    assert extractor.count_calls == 0
    assert extractor.extract_calls == 0
    assert service.usage_summary().calls == 0


# 驗證呼叫預算用完時連 count_tokens 都不再呼叫。
def test_budget_limit_skips_all_gemini_api_calls(tmp_path: Path) -> None:
    extractor = FakeGeminiExtractor()
    service = _service(tmp_path, extractor, max_calls=0)

    result = service.analyze("能源工程獎學金", _scanned_fetch_result("rules"))

    assert result is not None
    assert result.rule_text == ""
    assert result.diagnostic.status == "budget_skipped"
    assert extractor.count_calls == 0
    assert extractor.extract_calls == 0


# 主要辦法與證明文件皆為掃描檔時，Gemini 必須選主要辦法。
def test_rules_pdf_is_prioritized_over_supporting_document(tmp_path: Path) -> None:
    extractor = FakeGeminiExtractor()
    service = _service(tmp_path, extractor)
    source = _scanned_fetch_result().source
    supporting = ResourceDiagnostic(
        "attachment", "https://example.com/proof.pdf", "", "application/pdf",
        500, "pdf", "error", 0, "掃描檔", "supporting_document",
    )
    rules = ResourceDiagnostic(
        "attachment", "https://example.com/rules.pdf", "", "application/pdf",
        1000, "pdf", "error", 0, "掃描檔", "rules",
    )
    result = DetailFetchResult("申請資格請參閱附件。", source, (supporting, rules), 2)

    fallback = service.analyze("能源工程獎學金", result)

    assert fallback is not None
    assert extractor.prepared_urls == ["https://example.com/rules.pdf"]


# 只有次要證明文件為掃描檔時，不得浪費 Gemini 額度。
def test_supporting_document_alone_does_not_use_gemini(tmp_path: Path) -> None:
    extractor = FakeGeminiExtractor()
    service = _service(tmp_path, extractor)

    fallback = service.analyze(
        "一般獎學金",
        _scanned_fetch_result("supporting_document"),
    )

    assert fallback is None
    assert extractor.prepared_urls == []
    assert service.usage_summary().calls == 0
