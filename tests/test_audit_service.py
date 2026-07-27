# -*- coding: utf-8 -*-

from pathlib import Path

from src.collectors.base_collector import BaseCollector
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ScholarshipService


class FakeCollector(BaseCollector):
    """回傳指定公告的測試蒐集器。"""

    # 初始化固定公告清單。
    def __init__(self, items: list[Scholarship]) -> None:
        self.items = items

    # 回傳固定公告清單。
    def collect(self) -> list[Scholarship]:
        return self.items


class FakeDetailFetcher:
    """依公告網址回傳固定正文。"""

    # 初始化網址與正文對照。
    def __init__(self, details: dict[str, str]) -> None:
        self.details = details

    # 回傳指定公告正文。
    def fetch_text(self, scholarship: Scholarship) -> str:
        return self.details[scholarship.source_url]


# 建立匿名學生背景。
def _profile() -> StudentProfile:
    return StudentProfile(
        school="測試科技大學",
        degree_level="學士",
        program_type="進修部",
        department="電子工程系",
        year=2,
        employed=True,
        average_grade=90.34,
        conduct_grade=85,
        class_rank=1,
        class_size=17,
        residence="新北市",
        special_statuses=tuple(),
        research_keywords=("電力電子", "能源"),
    )


# 建立含稽核能力的測試服務。
def _service(
    tmp_path: Path,
    items: list[Scholarship],
    details: dict[str, str],
    sent_messages: list[str],
) -> tuple[ScholarshipService, ScholarshipRepository]:
    repository = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    service = ScholarshipService(
        FakeCollector(items),
        repository,
        sent_messages.append,
        include_keywords=("獎學金", "就學貸款"),
        summary_batch_size=5,
        detail_fetcher=FakeDetailFetcher(details),
        evaluator=EligibilityEvaluator(),
        profile=_profile(),
    )
    return service, repository


# 驗證 policy 公告不會進入正式推播。
def test_policy_notice_is_not_sent(tmp_path: Path) -> None:
    policy = Scholarship.from_raw(
        "lhu",
        "就學貸款作業要點部分條文修正案",
        "2026-07-01",
        "https://example.com/policy",
    )
    sent_messages: list[str] = []
    service, repository = _service(
        tmp_path,
        [policy],
        {policy.source_url: "本次公告修正就學貸款相關條文。"},
        sent_messages,
    )

    result = service.run(dry_run=False)

    assert result.notified_count == 0
    assert result.ineligible_count == 1
    assert sent_messages == []
    pending = repository.list_pending()
    assert pending[0].notice_kind == "policy"


# 驗證 audit 會重新檢查全部公告但不修改資料庫與通知狀態。
def test_audit_does_not_modify_repository_or_send_line(tmp_path: Path) -> None:
    item = Scholarship.from_raw(
        "lhu",
        "電力與能源工程獎學金",
        "2026-07-02",
        "https://example.com/application",
    )
    sent_messages: list[str] = []
    service, repository = _service(
        tmp_path,
        [item],
        {item.source_url: "大專院校電子相關科系在校生可申請。"},
        sent_messages,
    )

    result = service.audit()

    assert result.eligible_count == 1
    assert result.records[0].item.notice_kind == "application"
    assert repository.is_empty()
    assert sent_messages == []
