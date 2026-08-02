# -*- coding: utf-8 -*-

from types import SimpleNamespace

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.evaluators.application_evidence_scorer import ApplicationEvidence
from src.evaluators.eligibility_evaluator import (
    ELIGIBLE,
    INELIGIBLE,
    REVIEW,
    EligibilityDecision,
)
from src.evaluators.notice_classifier import APPLICATION
from src.models.eligibility_axes import VERIFY_SOURCE
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.services.revision_aware_scholarship_service import (
    RevisionAwareScholarshipService,
)
from src.services.scholarship_service import EvaluationOutcome


class _TextAnalysis:
    extraction = object()

    def analyze(self, title: str, fetch_result: DetailFetchResult) -> SimpleNamespace:
        _ = title, fetch_result
        return SimpleNamespace(extraction=self.extraction)


class _StructuredEvaluator:
    def __init__(self, status: str) -> None:
        self.status = status

    def evaluate(self, extraction: object, profile: StudentProfile) -> SimpleNamespace:
        _ = extraction, profile
        reason = "須具備以下任一身分：家庭清寒、經濟弱勢、遭逢變故。"
        return SimpleNamespace(decision=EligibilityDecision(self.status, (reason,)))


def _profile() -> StudentProfile:
    return StudentProfile(
        school="龍華科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.34,
        conduct_grade=86,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電力電子",),
    )


def _fetch_result() -> DetailFetchResult:
    text = "申請資格：須具備家庭清寒、經濟弱勢或遭逢變故其中一項。"
    source = ResourceDiagnostic(
        "source",
        "https://example.test/detail",
        "https://example.test/detail",
        "text/html",
        len(text.encode("utf-8")),
        "html",
        "success",
        len(text),
    )
    return DetailFetchResult(text, source, tuple(), 0, body_text=text)


def _outcome(status: str) -> EvaluationOutcome:
    return EvaluationOutcome(
        EligibilityDecision(status, ("legacy 判斷。",)),
        APPLICATION,
        "open",
        "申請資格正文",
        None,
        ApplicationEvidence(0, "navigation_or_wrong_page", tuple()),
        VERIFY_SOURCE,
    )


def _service(structured_status: str) -> RevisionAwareScholarshipService:
    service = object.__new__(RevisionAwareScholarshipService)
    service.gemini_text_analysis = _TextAnalysis()
    service.structured_evaluator = _StructuredEvaluator(structured_status)
    service.profile = _profile()
    return service


def test_structured_ineligible_vetoes_legacy_eligible() -> None:
    item = Scholarship.from_raw(
        "test",
        "台灣松樑教育公益促進協會助學金",
        "2026-08-01",
        "https://example.test/detail",
    )

    result = _service(INELIGIBLE)._apply_structured_ineligible_veto(
        item,
        _fetch_result(),
        _outcome(ELIGIBLE),
    )

    assert result.decision.status == INELIGIBLE
    assert result.action_status == "reject"


def test_structured_eligible_never_promotes_legacy_review() -> None:
    item = Scholarship.from_raw(
        "test",
        "一般獎學金開放申請",
        "2026-08-01",
        "https://example.test/detail",
    )

    result = _service(ELIGIBLE)._apply_structured_ineligible_veto(
        item,
        _fetch_result(),
        _outcome(REVIEW),
    )

    assert result.decision.status == REVIEW
