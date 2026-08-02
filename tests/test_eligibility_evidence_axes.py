# -*- coding: utf-8 -*-

from pathlib import Path

from src.collectors.base_collector import BaseCollector
from src.evaluators.eligibility_evaluator import ELIGIBLE, EligibilityDecision
from src.models.eligibility_axes import (
    APPLY_CANDIDATE,
    MANUAL_REVIEW,
    NOT_ACTIONABLE,
    REJECT,
    VERIFY_SOURCE,
    derive_action_status,
)
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ScholarshipService


class _Collector(BaseCollector):
    def __init__(self, item: Scholarship) -> None:
        self.item = item

    def collect(self) -> list[Scholarship]:
        return [self.item]


class _Fetcher:
    def __init__(self, text: str) -> None:
        self.text = text

    def fetch_text(self, scholarship: Scholarship) -> str:
        return self.text


class _EligibleEvaluator:
    def evaluate(
        self,
        scholarship: Scholarship,
        detail: object,
        profile: StudentProfile,
    ) -> EligibilityDecision:
        return EligibilityDecision(ELIGIBLE, ("學制、學位與科系硬性條件符合。",))


def _profile() -> StudentProfile:
    return StudentProfile(
        school="測試科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=None,
        conduct_grade=None,
        class_rank=None,
        class_size=None,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電力電子",),
    )


def test_action_status_is_derived_from_independent_axes() -> None:
    assert derive_action_status(
        "eligible", "valid_application_detail", "application", "open"
    ) == APPLY_CANDIDATE
    assert derive_action_status(
        "eligible", "insufficient_evidence", "application", "open"
    ) == VERIFY_SOURCE
    assert derive_action_status(
        "review", "valid_application_detail", "application", "open"
    ) == MANUAL_REVIEW
    assert derive_action_status(
        "ineligible", "insufficient_evidence", "application", "open"
    ) == REJECT
    assert derive_action_status(
        "eligible", "valid_application_detail", "result", "not_applicable"
    ) == NOT_ACTIONABLE


def test_insufficient_source_evidence_does_not_overwrite_hard_eligible(
    tmp_path: Path,
) -> None:
    item = Scholarship.from_raw(
        "test",
        "電力工程獎學金開放申請",
        "2026-08-01",
        "https://example.test/detail",
    )
    repository = ScholarshipRepository(tmp_path / "scholarships.db")
    service = ScholarshipService(
        _Collector(item),
        repository,
        lambda message: None,
        include_keywords=("獎學金",),
        summary_batch_size=5,
        detail_fetcher=_Fetcher("截止日期：2026年9月30日。"),
        evaluator=_EligibleEvaluator(),  # type: ignore[arg-type]
        profile=_profile(),
        notify_review_items=False,
    )

    result = service.audit()
    evaluated = result.records[0].item

    assert evaluated.hard_eligibility_status == "eligible"
    assert evaluated.eligibility_status == "eligible"
    assert evaluated.resolution_status == "insufficient_evidence"
    assert evaluated.action_status == VERIFY_SOURCE
    assert result.eligible_count == 1
    assert result.review_count == 0


def test_source_incomplete_hard_eligible_is_notifiable(tmp_path: Path) -> None:
    item = Scholarship.from_raw(
        "test",
        "能源人才獎學金開放申請",
        "2026-08-01",
        "https://example.test/energy",
    )
    repository = ScholarshipRepository(tmp_path / "scholarships.db")
    service = ScholarshipService(
        _Collector(item),
        repository,
        lambda message: None,
        include_keywords=("獎學金",),
        summary_batch_size=5,
        detail_fetcher=_Fetcher("截止日期：2026年9月30日。"),
        evaluator=_EligibleEvaluator(),  # type: ignore[arg-type]
        profile=_profile(),
        notify_review_items=False,
    )

    result = service.run(dry_run=True)

    assert result.eligible_count == 1
    assert result.review_count == 0
    assert len(result.pending_items) == 1
    assert result.pending_items[0].action_status == VERIFY_SOURCE
