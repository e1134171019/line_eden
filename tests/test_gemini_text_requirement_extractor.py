# -*- coding: utf-8 -*-

from types import SimpleNamespace

from src.ai.gemini_text_requirement_extractor import GeminiTextRequirementExtractor
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    ResourceDiagnostic,
    RULES_STATUS_RESOLVED,
)


class _Models:
    def __init__(self) -> None:
        self.last_contents: list[str] | None = None

    def count_tokens(self, model: str, contents: list[str]) -> SimpleNamespace:
        self.last_contents = contents
        return SimpleNamespace(total_tokens=120)


class _Extractor:
    def __init__(self) -> None:
        self.client = SimpleNamespace(models=_Models())
        self.model = "test-model"
        self.max_input_tokens = 5000
        self.max_output_tokens = 1200


def _fetch_result() -> DetailFetchResult:
    source = ResourceDiagnostic(
        "source", "https://example.com", "https://example.com", "text/html",
        100, "html", "success", 20,
    )
    attachment = ExtractedAttachment(
        "https://example.com/rules.pdf",
        "https://example.com/rules.pdf",
        "申請辦法.pdf",
        "rules",
        "scholarship_rules",
        "pdf",
        "success",
        "申請資格限電子工程相關科系，學業平均80分以上。",
    )
    return DetailFetchResult(
        "合併文字",
        source,
        tuple(),
        1,
        body_text="公告正文",
        extracted_attachments=(attachment,),
        rules_status=RULES_STATUS_RESOLVED,
    )


def test_prepare_includes_body_and_attachment_evidence() -> None:
    extractor = GeminiTextRequirementExtractor(_Extractor())

    prepared = extractor.prepare("能源獎學金", _fetch_result())

    assert "公告正文" in prepared.prompt
    assert "電子工程相關科系" in prepared.prompt
    assert "scholarship_rules" in prepared.prompt
    assert len(prepared.content_hash) == 64


def test_count_tokens_uses_text_prompt() -> None:
    base = _Extractor()
    extractor = GeminiTextRequirementExtractor(base)
    prepared = extractor.prepare("能源獎學金", _fetch_result())

    tokens = extractor.count_tokens(prepared)

    assert tokens == 120
    assert base.client.models.last_contents == [prepared.prompt]
