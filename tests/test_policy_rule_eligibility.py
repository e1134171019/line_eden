# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import RULES_STATUS_NOT_REQUIRED
from src.evaluators.application_evidence_scorer import (
    VALID_APPLICATION_DETAIL,
    ApplicationEvidence,
)
from src.evaluators.eligibility_evaluator import INELIGIBLE, EligibilityEvaluator
from src.evaluators.notice_classifier import POLICY
from src.evaluators.runtime_safety import NOT_APPLICABLE
from src.models.evaluator_input import EvaluatorInput
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.services.revision_aware_scholarship_service import (
    RevisionAwareScholarshipService,
)
from src.services.scholarship_service import ELIGIBILITY_NOT_APPLICABLE


def _profile() -> StudentProfile:
    return StudentProfile(
        school="龍華科技大學",
        degree_level="學士",
        program_type="進修部四技",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.6,
        conduct_grade=86.0,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電子", "電機", "電力"),
        special_statuses_confirmed=True,
    )


def _service() -> RevisionAwareScholarshipService:
    service = object.__new__(RevisionAwareScholarshipService)
    service.evaluator = EligibilityEvaluator()
    service.profile = _profile()
    return service


def _evidence() -> ApplicationEvidence:
    return ApplicationEvidence(
        5,
        VALID_APPLICATION_DETAIL,
        ("申請資格", "申請方式"),
    )


def test_known_policy_rules_preserve_hard_ineligible_without_becoming_actionable() -> None:
    item = Scholarship.from_raw(
        "tun-program-songliang-aid",
        "助學金實施辦法",
        "2026-08-02",
        "https://www.slceas.org.tw/index.php/scholarship/scholarship01",
        program_id="songliang-aid",
    )
    text = (
        "申請資格：就讀國內大專院校電子、電機相關學系學生，"
        "不含夜間部、推廣教育部及進修部學生。"
        "申請方式：備妥文件後提出申請。"
    )
    decision, notice_kind, application_status = _service()._evaluate_detail(
        item,
        text,
        EvaluatorInput(body_text=text, rules_status=RULES_STATUS_NOT_REQUIRED),
        _evidence(),
    )

    assert decision.status == INELIGIBLE
    assert "進修部" in decision.reason_text()
    assert notice_kind == POLICY
    assert application_status == NOT_APPLICABLE


def test_generic_policy_without_program_contract_remains_not_applicable() -> None:
    item = Scholarship.from_raw(
        "generic",
        "助學金實施辦法",
        "2026-08-02",
        "https://example.test/policy",
    )
    text = "申請資格：大專學生可申請。申請方式：填寫表單。"
    decision, notice_kind, application_status = _service()._evaluate_detail(
        item,
        text,
        EvaluatorInput(body_text=text, rules_status=RULES_STATUS_NOT_REQUIRED),
        _evidence(),
    )

    assert decision.status == ELIGIBILITY_NOT_APPLICABLE
    assert notice_kind == POLICY
    assert application_status == NOT_APPLICABLE
