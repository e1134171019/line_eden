# -*- coding: utf-8 -*-

from src.ai.gemini_requirement_extractor import GeminiRequirementExtraction
from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_DISCOVERED_UNRESOLVED
from src.evaluators.eligibility_evaluator import INELIGIBLE, REVIEW, EligibilityEvaluator
from src.models.evaluator_input import GEMINI_RULE_PARTIAL_EXCLUSIONS, EvaluatorInput
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.services.gemini_fallback_service import _usable_diagnostic, _usable_rule_text


# 建立沒有顱顏患者身分的學生背景。
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


# 建立測試公告。
def _item() -> Scholarship:
    return Scholarship.from_raw(
        "lhu",
        "羅慧夫得福獎助學金",
        "2026-06-09",
        "https://example.com/item",
    )


# 建立只含硬性身分證據的不完整抽取。
def _partial_extraction() -> GeminiRequirementExtraction:
    return GeminiRequirementExtraction(
        document_type="other",
        criteria_complete=False,
        needs_more_pages=True,
        required_special_statuses=["顱顏患者"],
        evidence=[{"page": 1, "text": "本獎助學金用以鼓勵顱顏患者。"}],
    )


# 建立明確標示為部分排除範圍的 typed evaluator 輸入。
def _partial_input(body_text: str, rule_text: str) -> EvaluatorInput:
    return EvaluatorInput(
        body_text=body_text,
        gemini_rule_text=rule_text,
        rules_status=RULES_STATUS_DISCOVERED_UNRESOLVED,
        gemini_rule_scope=GEMINI_RULE_PARTIAL_EXCLUSIONS,
    )


# 不完整抽取只輸出有證據的硬性身分，不得輸出成績或學位正向條件。
def test_incomplete_gemini_only_returns_evidenced_hard_exclusion() -> None:
    extraction = GeminiRequirementExtraction(
        document_type="other",
        criteria_complete=False,
        needs_more_pages=True,
        degree_levels=["大學生"],
        required_special_statuses=["顱顏患者"],
        minimum_average_grade=80,
        evidence=[{"page": 1, "text": "本獎助學金用以鼓勵顱顏患者。"}],
    )

    rule_text = _usable_rule_text(extraction)

    assert "顱顏患者" in rule_text
    assert "大學生" not in rule_text
    assert "80" not in rule_text
    assert "【" not in rule_text


# 有頁碼證據的硬性身分可將不符合者判為 ineligible。
def test_partial_gemini_status_excludes_non_matching_profile() -> None:
    rule_text = _usable_rule_text(_partial_extraction())

    decision = EligibilityEvaluator().evaluate(
        _item(),
        _partial_input("基金會網站含其他研究合作內容。", rule_text),
        _profile(),
    )

    assert decision.status == INELIGIBLE
    assert "顱顏患者" in decision.reason_text()


# 已具有該身分時仍因附件不完整維持 review，不得變成 eligible。
def test_partial_gemini_never_creates_eligible() -> None:
    rule_text = _usable_rule_text(_partial_extraction())

    decision = EligibilityEvaluator().evaluate(
        _item(),
        _partial_input("", rule_text),
        _profile(("顱顏患者",)),
    )

    assert decision.status == REVIEW


# Audit 診斷需明確標示部分硬性排除，而不是宣稱條件完整。
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
