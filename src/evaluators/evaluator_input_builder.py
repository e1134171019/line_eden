# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.models.evaluator_input import (
    GEMINI_RULE_NONE,
    EvaluatorInput,
    GeminiRuleScope,
)


def build_evaluator_input(
    fetch_result: DetailFetchResult,
    gemini_rule_text: str | None = None,
    *,
    gemini_rule_scope: GeminiRuleScope = GEMINI_RULE_NONE,
    rules_status: str | None = None,
) -> EvaluatorInput:
    """由結構化擷取結果建立 evaluator 輸入，不進行 marker 字串替換。"""
    resolved_rules = tuple(
        attachment.text.strip()
        for attachment in fetch_result.extracted_attachments
        if attachment.status == "success"
        and attachment.content_role == "scholarship_rules"
        and attachment.text.strip()
    )
    return EvaluatorInput(
        body_text=(fetch_result.body_text or fetch_result.text).strip(),
        resolved_attachment_texts=resolved_rules,
        gemini_rule_text=(gemini_rule_text.strip() if gemini_rule_text else None),
        rules_status=rules_status or fetch_result.rules_status,
        gemini_rule_scope=gemini_rule_scope,
    )
