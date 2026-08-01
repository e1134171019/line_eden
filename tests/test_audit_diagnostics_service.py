# -*- coding: utf-8 -*-

from pathlib import Path

from src.collectors.base_collector import BaseCollector
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.notifiers.notification_dispatcher import NotificationFanout
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ScholarshipService


class FakeCollector(BaseCollector):
    """回傳單一測試公告。"""

    # 初始化公告。
    def __init__(self, item: Scholarship) -> None:
        self.item = item

    # 回傳固定公告。
    def collect(self) -> list[Scholarship]:
        return [self.item]


class FailedDiagnosticFetcher:
    """模擬短網址最終下載失敗。"""

    # 回傳來源失敗診斷。
    def fetch_with_diagnostics(self, item: Scholarship) -> DetailFetchResult:
        source = ResourceDiagnostic(
            "source", item.source_url, "https://example.com/missing.pdf",
            "text/html", 0, "unknown", "error", 0,
            "HTTPStatusError: 404 Not Found",
        )
        return DetailFetchResult("", source, tuple(), 0)

    # 正式流程不應在本測試中呼叫。
    def fetch_text(self, _: Scholarship) -> str:
        raise AssertionError("audit 應使用 fetch_with_diagnostics")


# 建立匿名學生背景。
def _profile() -> StudentProfile:
    return StudentProfile(
        school="測試科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90,
        conduct_grade=85,
        class_rank=1,
        class_size=20,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電力", "能源"),
    )


# 驗證 audit 將來源錯誤保留在記錄且不修改資料庫。
def test_audit_record_keeps_source_diagnostic(tmp_path: Path) -> None:
    item = Scholarship.from_raw(
        "lhu", "希望獎助學金", "2026-07-27", "https://reurl.cc/missing",
    )
    repository = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    service = ScholarshipService(
        FakeCollector(item), repository, NotificationFanout(tuple()),
        include_keywords=("獎學金", "助學金"),
        summary_batch_size=5,
        detail_fetcher=FailedDiagnosticFetcher(),
        evaluator=EligibilityEvaluator(),
        profile=_profile(),
    )

    result = service.audit()

    record = result.records[0]
    assert record.item.notice_kind == "unknown"
    assert record.item.eligibility_status == "review"
    assert "404 Not Found" in record.fetch_result.source.error
    assert repository.is_empty()
