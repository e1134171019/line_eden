# -*- coding: utf-8 -*-

from types import SimpleNamespace

from src.ai.gemini_requirement_extractor import GeminiRequirementExtractor


class FakeModels:
    def __init__(self) -> None:
        self.last_contents: list[object] | None = None

    def count_tokens(self, model: str, contents: list[object]) -> SimpleNamespace:
        assert model == "test-model"
        self.last_contents = contents
        return SimpleNamespace(total_tokens=321)

    def generate_content(
        self,
        model: str,
        contents: list[object],
        config: object,
    ) -> SimpleNamespace:
        assert model == "test-model"
        assert config is not None
        self.last_contents = contents
        return SimpleNamespace(
            text=(
                '{"document_type":"scholarship_rules",'
                '"criteria_complete":true,'
                '"needs_more_pages":false,'
                '"applicant_groups":["大專校院在校生"],'
                '"departments_included":["電子工程相關科系"],'
                '"minimum_average_grade":80,'
                '"evidence":[{"source_kind":"body",'
                '"source_index":null,"page":null,'
                '"text":"電子工程相關科系可申請"}]}'
            ),
            usage_metadata=SimpleNamespace(
                prompt_token_count=120,
                candidates_token_count=30,
                total_token_count=150,
            ),
        )


def _extractor() -> tuple[GeminiRequirementExtractor, FakeModels]:
    extractor = object.__new__(GeminiRequirementExtractor)
    models = FakeModels()
    extractor.client = SimpleNamespace(models=models)
    extractor.model = "test-model"
    extractor.max_input_tokens = 5000
    extractor.max_output_tokens = 1200
    return extractor, models


def test_count_text_tokens_uses_body_and_attachment_text() -> None:
    extractor, models = _extractor()

    tokens = extractor.count_text_tokens(
        "能源獎學金",
        "申請對象為大專校院在校生。",
        ["申請資格限電子工程相關科系。"],
    )

    assert tokens == 321
    prompt = str(models.last_contents[0])
    assert "公告正文" in prompt
    assert "附件文字 1" in prompt
    assert "電子工程" in prompt


def test_extract_from_text_returns_structured_evidence() -> None:
    extractor, _ = _extractor()

    result = extractor.extract_from_text(
        "能源獎學金",
        "申請對象為大專校院在校生。",
        ["申請資格限電子工程相關科系。"],
    )

    assert result.extraction.criteria_complete is True
    assert result.extraction.departments_included == ["電子工程相關科系"]
    assert result.extraction.evidence[0].source_kind == "body"
    assert result.extraction.evidence[0].page is None
    assert result.input_tokens == 120
    assert result.output_tokens == 30
