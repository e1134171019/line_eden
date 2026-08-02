# -*- coding: utf-8 -*-

from pathlib import Path

from src.collectors.base_collector import BaseCollector
from src.evaluators.eligibility_evaluator import ELIGIBLE, EligibilityDecision
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.repositories.sqlite_connection import open_database
from src.services.revision_aware_scholarship_service import (
    RevisionAwareScholarshipService,
)


class _Collector(BaseCollector):
    def __init__(self, item: Scholarship) -> None:
        self.item = item

    def collect(self) -> list[Scholarship]:
        return [self.item]


class _Fetcher:
    def __init__(self, text: str, *, fail: bool = False) -> None:
        self.text = text
        self.fail = fail

    def fetch_text(self, scholarship: Scholarship) -> str:
        if self.fail:
            raise RuntimeError("source unavailable")
        return self.text


class _Evaluator:
    def evaluate(
        self,
        scholarship: Scholarship,
        detail: object,
        profile: StudentProfile,
    ) -> EligibilityDecision:
        return EligibilityDecision(ELIGIBLE, ("硬性條件符合。",))


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


def _service(
    item: Scholarship,
    repository: ScholarshipRepository,
    text: str,
    *,
    fail: bool = False,
) -> RevisionAwareScholarshipService:
    return RevisionAwareScholarshipService(
        _Collector(item),
        repository,
        lambda message: None,
        include_keywords=("獎學金",),
        summary_batch_size=5,
        detail_fetcher=_Fetcher(text, fail=fail),  # type: ignore[arg-type]
        evaluator=_Evaluator(),  # type: ignore[arg-type]
        profile=_profile(),
    )


def _body(extra: str = "") -> str:
    return (
        "申請資格：國內大專校院學生可申請。"
        "申請方式：線上填表。"
        "截止日期：2026年9月30日。"
        f"{extra}"
    )


def test_first_revision_baseline_does_not_resend_existing_notice(tmp_path: Path) -> None:
    repository = ScholarshipRepository(tmp_path / "state.db")
    item = Scholarship.from_raw(
        "test",
        "能源獎學金開放申請",
        "2026-08-01",
        "https://example.test/detail",
    )
    repository.discover([item])
    repository.mark_eligibility(
        item.content_hash,
        "eligible",
        "硬性條件符合。",
        _profile().fingerprint(),
        "application",
        "open",
        resolution_status="valid_application_detail",
    )
    repository.mark_notified([item.content_hash])
    result = _service(item, repository, _body()).run(dry_run=True)
    assert result.pending_items == []
    with open_database(repository.db_path) as conn:
        notified = conn.execute(
            "SELECT notified_at FROM scholarships WHERE content_hash = ?",
            [item.content_hash],
        ).fetchone()
    assert notified is not None and notified[0] is not None


def test_changed_revision_reopens_and_reuses_fetched_content(tmp_path: Path) -> None:
    repository = ScholarshipRepository(tmp_path / "state.db")
    item = Scholarship.from_raw(
        "test",
        "能源獎學金開放申請",
        "2026-08-01",
        "https://example.test/detail",
    )
    repository.discover([item])
    first = _service(item, repository, _body())
    first.run(dry_run=True)
    repository.mark_notified([item.content_hash])
    changed = _service(item, repository, _body("新增電子工程系優先。"))
    result = changed.run(dry_run=True)
    assert len(result.pending_items) == 1
    assert result.pending_items[0].hard_eligibility_status == "eligible"
    with open_database(repository.db_path) as conn:
        notified = conn.execute(
            "SELECT notified_at FROM scholarships WHERE content_hash = ?",
            [item.content_hash],
        ).fetchone()
    assert notified == (None,)


def test_source_failure_does_not_create_empty_revision(tmp_path: Path) -> None:
    repository = ScholarshipRepository(tmp_path / "state.db")
    item = Scholarship.from_raw(
        "test",
        "能源獎學金開放申請",
        "2026-08-01",
        "https://example.test/detail",
    )
    _service(item, repository, "", fail=True).run(dry_run=True)
    with open_database(repository.db_path) as conn:
        count = conn.execute("SELECT COUNT(1) FROM announcement_revisions").fetchone()
    assert count == (0,)
