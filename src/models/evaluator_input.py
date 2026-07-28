# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import StrEnum


class GeminiRuleScope(StrEnum):
    """描述 Gemini 規則文字可被信任的範圍。"""

    NONE = "none"
    COMPLETE = "complete"
    PARTIAL_EXCLUSIONS = "partial_exclusions"


GEMINI_RULE_NONE = GeminiRuleScope.NONE
GEMINI_RULE_COMPLETE = GeminiRuleScope.COMPLETE
GEMINI_RULE_PARTIAL_EXCLUSIONS = GeminiRuleScope.PARTIAL_EXCLUSIONS


@dataclass(frozen=True)
class EvaluatorInput:
    """資格評估的結構化輸入；不使用 marker 傳遞附件狀態。"""

    body_text: str
    resolved_attachment_texts: tuple[str, ...] = tuple()
    gemini_rule_text: str | None = None
    rules_status: str = "unknown"
    gemini_rule_scope: GeminiRuleScope = GeminiRuleScope.NONE
