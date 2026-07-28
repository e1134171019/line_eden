# -*- coding: utf-8 -*-

from src.ai.gemini_requirement_extractor import GeminiRequirementExtraction
from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_DISCOVERED_UNRESOLVED
from src.evaluators.eligibility_evaluator import INELIGIBLE, REVIEW, EligibilityEvaluator
from src.models.evaluator_input import GEMINI_RULE_PARTIAL_EXCLUSIONS, EvaluatorInput
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.services.gemini_fallback_service import _usable_diagnostic, _usable_rule_text


def _profile(statuses: tuple[str, ...] = tuple()) -> StudentProfile:
    return StudentProfile(
        school="龍華科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.34,
        conduct_grade=85,
        class_rank=1,
        class_size=17,
        residence="",
        special_statuses=statuses,
        research_keywords=("電力電子",),
    )


def _item() -> Scholarship:
    return Scholarship.from_raw(
        "lhu",
        "羅慧夫得福獎助學金",
        "2026-06-09",
        "https://example.com/item",
    )


def _partial_extraction() -> GeminiRequirementExtraction:
    return GeminiRequirementExtraction(
        document_type="other",
        criteria_complete=False,
        needs_more_pages=True,
        required_special_statuses=["顱顏患者"],
        evidence=[{"page": 1, "text": "本獎助學金用以鼓勵顱顏患者。"}],
    )


def _input(body: str, rule_text: str) -> EvaluatorInput:
    return EvaluatorInput(
        body_text=body,
        gemini_rule_text=rule_text,
        rules_status=RULES_STATUS_DISCOVERED_UNRESOLVED,
        gemini_rule_scope=GEMINI_RULE_PARTIAL_EXCLUSIONS,
    )


def test_incomplete_gemini_only_returns_evidenced_hard_exclusion() -> None:
    extraction = _partial_extraction()
    extraction.degree_levels = ["大學生"]
    extraction.minimum_average_grade = 80

    rule_text = _usable_rule_text(extraction)

    assert "顱顏患者" in rule_text
    assert "大學生" not in rule_text
    assert "80" not in rule_text
    assert "【" not in rule_text


def test_partial_gemini_status_excludes_non_matching_profile() -> None:
    rule_text = _usable_rule_text(_partial_extraction())
    decision = EligibilityEvaluator().evaluate(
        _item(),
        _input("基金會網站含其他研究合作內容。", rule_text),
        _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "顱顏患者" in decision.reason_text()


def test_partial_gemini_never_creates_eligible() -> None:
    rule_text = _usable_rule_text(_partial_extraction())
    decision = EligibilityEvaluator().evaluate(
        _item(),
        _input("", rule_text),
        _profile(("顱顏患者",)),
    )

    assert decision.status == REVIEW


def test_partial_gemini_diagnostic_is_explicit() -> None:
    diagnostic = _usable_diagnostic(
        _partial_extraction(),
        "https://example.com/rules.pdf",
        "test-model",
        False,
        2,
        100,
        20,
        120,
    )

    assert diagnostic.status == "partial_exclusion"
    assert "尚未完整" in diagnostic.message
