# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.models.evaluator_input import (
    GEMINI_RULE_NONE,
    EvaluatorInput,
    GeminiRuleScope,
)


# 純函式：正規化 Gemini 規則文字並拒絕互相矛盾的 scope。
def _normalize_gemini_rule(
    gemini_rule_text: str | None,
    gemini_rule_scope: GeminiRuleScope,
) -> tuple[str | None, GeminiRuleScope]:
    """純函式：確保 Gemini 規則文字與信任範圍保持一致。"""
    normalized_text = gemini_rule_text.strip() if gemini_rule_text else None
    if normalized_text is None:
        if gemini_rule_scope is not GEMINI_RULE_NONE:
            raise ValueError("Gemini 規則 scope 非 none 時必須提供規則文字")
        return None, GEMINI_RULE_NONE
    if gemini_rule_scope is GEMINI_RULE_NONE:
        raise ValueError("提供 Gemini 規則文字時必須指定可信 scope")
    return normalized_text, gemini_rule_scope


# 純函式：從結構化擷取結果建立 evaluator 輸入。
def build_evaluator_input(
    fetch_result: DetailFetchResult,
    gemini_rule_text: str | None = None,
    *,
    gemini_rule_scope: GeminiRuleScope = GEMINI_RULE_NONE,
    rules_status: str | None = None,
) -> EvaluatorInput:
    """純函式：建立不含 marker 語意的資格評估輸入。"""
    content = fetch_result.content
    resolved_rules = tuple(
        attachment.text.strip()
        for attachment in content.attachments
        if attachment.status == "success"
        and attachment.content_role == "scholarship_rules"
        and attachment.text.strip()
    )
    normalized_rule, normalized_scope = _normalize_gemini_rule(
        gemini_rule_text,
        gemini_rule_scope,
    )
    return EvaluatorInput(
        body_text=content.main_text.strip(),
        resolved_attachment_texts=resolved_rules,
        gemini_rule_text=normalized_rule,
        rules_status=content.rules_status if rules_status is None else rules_status,
        gemini_rule_scope=normalized_scope,
    )
