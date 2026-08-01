# -*- coding: utf-8 -*-

from pathlib import Path

from src.catalogs.tun_2025_program_catalog import ScholarshipProgramWatch
from src.collectors.base_collector import BaseCollector
from src.collectors.tun_program_watch_collector import (
    TunProgramWatchCollector,
    _extract_program_notices,
)
from src.evaluators.eligibility_evaluator import EligibilityEvaluator
from src.models.scholarship import Scholarship
from src.profiles.student_profile import StudentProfile
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import (
    ELIGIBILITY_NOT_APPLICABLE,
    ScholarshipService,
)


class _FakeCollector(BaseCollector):
    def __init__(self, items: list[Scholarship]) -> None:
        self.items = items

    def collect(self) -> list[Scholarship]:
        return self.items


class _FakeDetailFetcher:
    def __init__(self, details: dict[str, str]) -> None:
        self.details = details

    def fetch_text(self, scholarship: Scholarship) -> str:
        return self.details[scholarship.source_url]


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
        research_keywords=("逆變器", "電力電子", "能源"),
    )


def _repository(tmp_path: Path) -> ScholarshipRepository:
    return ScholarshipRepository(tmp_path / "data" / "scholarships.db")


# 38 項方案在任何網路請求前就必須具有明確來源狀態。
def test_all_tun_programs_have_source_state() -> None:
    collector = TunProgramWatchCollector(1.0, "test-agent")

    assert len(collector.program_states) == 38
    assert all(item.program_id and item.status for item in collector.program_states)


# 列表已找到獨立公告連結時，不得只因列表沒有發布日期而刪除候選。
def test_tun_candidate_without_listing_date_is_retained() -> None:
    program = ScholarshipProgramWatch(
        "auden-test",
        "耀登炳南大專校院優秀人才獎學金",
        "耀登炳南教育基金會",
        ("耀登炳南大專校院優秀人才獎學金",),
        "https://www.auden.com.tw/news-4/",
        "verified",
    )
    html = """
    <article>
      <a href="/2026scholarship/">
        2026耀登炳南大專院校優秀人才獎學金
      </a>
    </article>
    """

    records, matched = _extract_program_notices(
        html,
        program.official_url,
        (program,),
    )

    assert matched >= 1
    assert len(records) == 1
    assert records[0].published_date == ""
    assert records[0].program_id == "auden-test"
    assert records[0].entry_url == program.official_url
    assert records[0].detail_url == "https://www.auden.com.tw/2026scholarship/"


# 已知 catalog 方案不受通用標題關鍵字誤刪，未知行政公告需留下排除理由。
def test_known_program_bypasses_generic_filter_and_exclusion_is_auditable(
    tmp_path: Path,
) -> None:
    known = Scholarship.from_raw(
        "tun-program-foxconn-scholarship-whale",
        "鴻海獎學鯨",
        "",
        "https://example.com/whale",
        program_id="foxconn-scholarship-whale",
        entry_url="https://example.com/",
    )
    unrelated = Scholarship.from_raw(
        "lhu",
        "教務處一般行政公告",
        "2026-08-01",
        "https://example.com/admin",
    )
    service = ScholarshipService(
        _FakeCollector([known, unrelated]),
        _repository(tmp_path),
        lambda _: None,
        include_keywords=("獎學金", "助學金"),
        summary_batch_size=5,
    )

    result = service.run(dry_run=True)

    assert result.collected == [known]
    assert len(result.exclusions) == 1
    assert result.exclusions[0].item.title == unrelated.title
    assert "未命中" in result.exclusions[0].reason
    assert result.pipeline_counts.raw_collected == 2
    assert result.pipeline_counts.relevance_accepted == 1
    assert result.pipeline_counts.relevance_excluded == 1


# 結果公告與已截止公告不再列為個人資格不符，只有未截止申請進 LINE 候選。
def test_notice_period_and_eligibility_are_separate(tmp_path: Path) -> None:
    result_item = Scholarship.from_raw(
        "lhu",
        "優秀學生獎學金得獎公告",
        "2026-08-01",
        "https://example.com/result",
    )
    expired_item = Scholarship.from_raw(
        "lhu",
        "清寒學生獎學金申請公告",
        "2025-01-01",
        "https://example.com/expired",
    )
    open_item = Scholarship.from_raw(
        "lhu",
        "電子工程學生獎學金申請公告",
        "2026-08-01",
        "https://example.com/open",
    )
    details = {
        result_item.source_url: "本年度獲獎名單如下。",
        expired_item.source_url: "申請期間至2025年2月1日止。",
        open_item.source_url: (
            "申請期間至2099年9月30日止。"
            "大專在校生，電子工程相關科系可申請。"
        ),
    }
    repository = _repository(tmp_path)
    service = ScholarshipService(
        _FakeCollector([result_item, expired_item, open_item]),
        repository,
        lambda _: None,
        include_keywords=("獎學金", "助學金"),
        summary_batch_size=5,
        detail_fetcher=_FakeDetailFetcher(details),
        evaluator=EligibilityEvaluator(),
        profile=_profile(),
        notify_review_items=True,
    )

    result = service.run(dry_run=True)
    stored = {item.source_url: item for item in repository.list_pending()}

    assert [item.source_url for item in result.pending_items] == [open_item.source_url]
    assert stored[result_item.source_url].notice_kind == "result"
    assert stored[result_item.source_url].eligibility_status == ELIGIBILITY_NOT_APPLICABLE
    assert stored[expired_item.source_url].application_status == "expired"
    assert stored[expired_item.source_url].eligibility_status == ELIGIBILITY_NOT_APPLICABLE
    assert stored[open_item.source_url].notice_kind == "application"
    assert stored[open_item.source_url].application_status == "open"
    assert stored[open_item.source_url].eligibility_status in {"eligible", "review"}
    assert result.pipeline_counts.evaluated_pending == 3
    assert result.pipeline_counts.application == 2
    assert result.pipeline_counts.non_application == 1
    assert result.pipeline_counts.notifiable == 1
