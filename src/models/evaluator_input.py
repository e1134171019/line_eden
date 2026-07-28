# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Literal

GEMINI_RULE_NONE = "none"
GEMINI_RULE_COMPLETE = "complete"
GEMINI_RULE_PARTIAL_EXCLUSIONS = "partial_exclusions"
GeminiRuleScope = Literal["none", "complete", "partial_exclusions"]


@dataclass(frozen=True)
class EvaluatorInput:
    """資格評估的結構化輸入；不使用 marker 傳遞附件狀態。"""

    body_text: str
    resolved_attachment_texts: tuple[str, ...] = tuple()
    gemini_rule_text: str | None = None
    rules_status: str = "unknown"
    gemini_rule_scope: GeminiRuleScope = GEMINI_RULE_NONE
