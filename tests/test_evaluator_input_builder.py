# -*- coding: utf-8 -*-

import pytest

from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ExtractedAttachment,
    ResourceDiagnostic,
    RULES_STATUS_DISCOVERED_UNRESOLVED,
    RULES_STATUS_RESOLVED,
)
from src.evaluators.evaluator_input_builder import build_evaluator_input
from src.models.evaluator_input import (
    GEMINI_RULE_COMPLETE,
    GEMINI_RULE_NONE,
)


def _source() -> ResourceDiagnostic:
    return ResourceDiagnostic(
        "source",
        "https://example.com/notice",
        "https://example.com/notice",
        "text/html",
        100,
        "html",
        "success",
        20,
    )


def _fetch_result() -> DetailFetchResult:
    return DetailFetchResult(
        "主文",
        _source(),
        tuple(),
        0,
        body_text="主文",
    )


def test_builder_excludes_unresolved_and_non_rule_attachments() -> None:
    unresolved = ExtractedAttachment(
        "https://example.com/a.pdf",
        "https://example.com/a.pdf",
        "附件一",
        "generic_attachment",
        "uncertain",
        "pdf",
        "error",
        "",
        "掃描 PDF 未解析",
    )
    supporting = ExtractedAttachment(
        "https://example.com/b.pdf",
        "https://example.com/b.pdf",
        "聲明書",
        "supporting_document",
        "supporting_document",
        "pdf",
        "success",
        "本人聲明內容",
    )
    rules = ExtractedAttachment(
        "https://example.com/rules.pdf",
        "https://example.com/rules.pdf",
        "申請辦法",
        "rules",
        "scholarship_rules",
        "pdf",
        "success",
        "申請資格限電子工程相關科系。",
    )
    fetch_result = DetailFetchResult(
        "legacy text",
        _source(),
        tuple(),
        3,
        body_text="公告主文",
        extracted_attachments=(unresolved, supporting, rules),
        rules_status=RULES_STATUS_DISCOVERED_UNRESOLVED,
    )

    result = build_evaluator_input(fetch_result)

    assert result.body_text == "公告主文"
    assert result.resolved_attachment_texts == ("申請資格限電子工程相關科系。",)
    assert result.gemini_rule_text is None
    assert result.gemini_rule_scope is GEMINI_RULE_NONE
    assert result.rules_status == RULES_STATUS_DISCOVERED_UNRESOLVED


def test_builder_passes_gemini_rule_without_mutating_other_fields() -> None:
    result = build_evaluator_input(
        _fetch_result(),
        "學業平均80分以上。",
        gemini_rule_scope=GEMINI_RULE_COMPLETE,
        rules_status=RULES_STATUS_RESOLVED,
    )

    assert result.body_text == "主文"
    assert result.resolved_attachment_texts == tuple()
    assert result.gemini_rule_text == "學業平均80分以上。"
    assert result.gemini_rule_scope is GEMINI_RULE_COMPLETE
    assert result.rules_status == RULES_STATUS_RESOLVED


def test_builder_rejects_rule_text_without_trust_scope() -> None:
    with pytest.raises(ValueError, match="可信 scope"):
        build_evaluator_input(_fetch_result(), "學業平均80分以上。")


def test_builder_rejects_scope_without_rule_text() -> None:
    with pytest.raises(ValueError, match="必須提供規則文字"):
        build_evaluator_input(
            _fetch_result(),
            gemini_rule_scope=GEMINI_RULE_COMPLETE,
        )
