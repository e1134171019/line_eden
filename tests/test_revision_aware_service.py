# -*- coding: utf-8 -*-

from pathlib import Path

from src.collectors.base_collector import BaseCollector
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.revision_aware_scholarship_service import RevisionAwareScholarshipService


class FakeCollector(BaseCollector):
    def __init__(self, item: Scholarship) -> None:
        self.item = item

    def collect(self) -> list[Scholarship]:
        return [self.item]


class MutableDetailFetcher:
    def __init__(self, text: str) -> None:
        self.text = text

    def fetch_with_diagnostics(self, scholarship: Scholarship) -> DetailFetchResult:
        url = scholarship.detail_url or scholarship.source_url
        source = ResourceDiagnostic(
            "source",
            url,
            url,
            "text/html",
            len(self.text.encode("utf-8")),
            "html",
            "success",
            len(self.text),
        )
        return DetailFetchResult(
            self.text,
            source,
            tuple(),
            0,
            body_text=self.text,
            rules_status="not_required",
        )


def _profile() -> StudentProfile:
    return StudentProfile(
        school="測試科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=0,
        conduct_grade=0,
        class_rank=0,
        class_size=0,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電子", "電力", "能源"),
    )


def _body(deadline: str) -> str:
    return (
        "申請對象為大專院校在校生，電子工程相關科系可申請。"
        f"申請截止日期為{deadline}。申請方式採線上申請。"
    )


def test_same_revision_does_not_resend_but_changed_revision_does(tmp_path: Path) -> None:
    item = Scholarship.from_raw(
        "source",
        "能源工程獎學金",
        "2026-08-01",
        "https://example.test/list/88",
        detail_url="https://example.test/detail/88",
    )
    fetcher = MutableDetailFetcher(_body("2026年12月31日"))
    sent: list[str] = []
    repository = ScholarshipRepository(tmp_path / "scholarships.db")
    service = RevisionAwareScholarshipService(
        FakeCollector(item),
        repository,
        sent.append,
        include_keywords=("獎學金",),
        summary_batch_size=5,
        detail_fetcher=fetcher,
        evaluator=EligibilityEvaluator(),
        profile=_profile(),
        notify_review_items=False,
    )

    first = service.run(dry_run=False)
    second = service.run(dry_run=False)
    fetcher.text = _body("2027年1月31日")
    third = service.run(dry_run=False)

    assert first.notified_count == 1
    assert second.notified_count == 0
    assert third.notified_count == 1
    assert len(sent) == 2
    assert "2026年12月31日" not in sent[1]
