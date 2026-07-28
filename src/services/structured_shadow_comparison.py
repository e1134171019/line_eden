# -*- coding: utf-8 -*-

from dataclasses import dataclass

from src.ai.gemini_requirement_extractor import GeminiRequirementExtraction
from src.evaluators.eligibility_evaluator import EligibilityDecision
from src.evaluators.structured_eligibility_evaluator import (
    ConditionResult,
    StructuredEligibilityEvaluator,
)
from src.profiles.student_profile import StudentProfile


@dataclass(frozen=True)
class StructuredShadowComparison:
    """保留正式 legacy 結果並記錄結構化 shadow 差異。"""

    legacy_status: str
    structured_status: str
    changed: bool
    legacy_reason: str
    structured_reason: str
    conditions: tuple[ConditionResult, ...]


def compare_legacy_and_structured(
    legacy: EligibilityDecision,
    extraction: GeminiRequirementExtraction,
    profile: StudentProfile,
    evaluator: StructuredEligibilityEvaluator | None = None,
) -> StructuredShadowComparison:
    structured = (evaluator or StructuredEligibilityEvaluator()).evaluate(extraction, profile)
    return StructuredShadowComparison(
        legacy.status,
        structured.decision.status,
        legacy.status != structured.decision.status,
        legacy.reason_text(),
        structured.decision.reason_text(),
        structured.conditions,
    )
