# -*- coding: utf-8 -*-

from io import BytesIO
from types import SimpleNamespace

from pypdf import PdfWriter

from src.ai.gemini_requirement_extractor import (
    GeminiRequirementExtraction,
    GeminiRequirementExtractor,
    PreparedGeminiDocument,
    RequirementEvidence,
    _build_pdf_prompt,
)


class FakeModels:
    """模擬 google-genai models 介面。"""

    def count_tokens(self, **kwargs: object) -> object:
        return SimpleNamespace(total_tokens=321)

    def generate_content(self, **kwargs: object) -> object:
        extraction = GeminiRequirementExtraction(
            document_type="scholarship_rules",
            criteria_complete=True,
            needs_more_pages=False,
            applicant_groups=["大專院校在校生"],
            minimum_average_grade=80,
            evidence=[RequirementEvidence(page=1, text="學業平均八十分以上")],
        )
        usage = SimpleNamespace(
            prompt_token_count=330,
            candidates_token_count=70,
            total_token_count=400,
        )
        return SimpleNamespace(text=extraction.model_dump_json(), usage_metadata=usage)


def _extractor(max_pages: int = 2, max_input_tokens: int = 1000) -> GeminiRequirementExtractor:
    extractor = GeminiRequirementExtractor(
        api_key="test-key",
        model="gemini-test",
        max_pages=max_pages,
        max_download_bytes=1024 * 1024,
        max_input_tokens=max_input_tokens,
        max_output_tokens=500,
        timeout_seconds=5,
        user_agent="test",
    )
    extractor.client = SimpleNamespace(models=FakeModels())
    return extractor


def _pdf_bytes(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_select_pages_limits_pdf_input() -> None:
    selected, page_count = _extractor(max_pages=2)._select_pages(_pdf_bytes(5))

    assert page_count == 2
    assert len(selected) < len(_pdf_bytes(5))


def test_count_and_extract_structured_requirements() -> None:
    extractor = _extractor()
    document = PreparedGeminiDocument(
        "https://example.com/a.pdf",
        "https://example.com/a.pdf",
        "hash",
        _pdf_bytes(1),
        1,
    )

    counted = extractor.count_tokens("測試獎學金", document)
    result = extractor.extract("測試獎學金", document)

    assert counted == 321
    assert result.extraction.minimum_average_grade == 80
    assert result.input_tokens == 330
    assert result.output_tokens == 70


def test_prompt_does_not_request_student_profile() -> None:
    prompt = _build_pdf_prompt("能源獎學金", 2)

    assert "只抽取文件" in prompt
    assert "profile.json" not in prompt
    assert "學生是否符合" in prompt


def test_extraction_builds_deterministic_rule_text() -> None:
    extraction = GeminiRequirementExtraction(
        document_type="scholarship_rules",
        criteria_complete=True,
        needs_more_pages=False,
        applicant_groups=["大專院校在校生"],
        program_types_excluded=["進修部"],
        required_special_statuses=["低收入戶"],
        minimum_average_grade=80,
        evidence=[RequirementEvidence(page=1, text="申請資格")],
    )

    text = extraction.to_rule_text()

    assert "申請對象為大專院校在校生" in text
    assert "不包括進修部" in text
    assert "申請資格限於低收入戶" in text
    assert "學業平均80分以上" in text


def test_multiple_program_types_are_joined_in_one_rule() -> None:
    extraction = GeminiRequirementExtraction(
        document_type="scholarship_rules",
        criteria_complete=True,
        needs_more_pages=False,
        program_types_included=["日間部", "進修部"],
        evidence=[RequirementEvidence(page=1, text="日間部及進修部均可申請")],
    )

    assert "申請對象為日間部及進修部學生" in extraction.to_rule_text()
