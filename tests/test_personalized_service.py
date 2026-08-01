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

    def __init__(self, items: list[Scholarship]) -> None:
        self.items = items

    def collect(self) -> list[Scholarship]:
        return self.items


class FakeDetailFetcher:
    """依公告網址回傳固定內文。"""

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


def _item(index: int, title: str) -> Scholarship:
    return Scholarship.from_raw(
        "lhu",
        title,
        f"2026-07-{index:02d}",
        f"https://example.com/{index}",
    )


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
        include_keywords=("獎學金", "助學金", "就學貸款"),
        summary_batch_size=5,
        detail_fetcher=FakeDetailFetcher(details),
        evaluator=EligibilityEvaluator(),
        profile=_profile(),
        notify_review_items=False,
    )
    return service, repository


def test_personalized_dry_run_only_returns_eligible(tmp_path: Path) -> None:
    day_item = _item(1, "日間部學生獎學金")
    energy_item = _item(2, "電力與能源優秀學生獎學金")
    unknown_item = _item(3, "希望獎助學金")
    items = [day_item, energy_item, unknown_item]
    details = {
        day_item.source_url: "限日間部學生申請。",
        energy_item.source_url: (
            "大專在校生之電子工程相關科系可申請，學業平均 80 分以上。"
        ),
        unknown_item.source_url: "詳細資格請參閱附件。",
    }
    sent_messages: list[str] = []
    service, _ = _service(tmp_path, items, details, sent_messages)

    result = service.run(dry_run=True)

    assert [item.title for item in result.pending_items] == [energy_item.title]
    assert result.eligible_count == 1
    assert result.review_count == 1
    assert result.ineligible_count == 1
    assert sent_messages == []


def test_live_mode_only_sends_eligible_item(tmp_path: Path) -> None:
    day_item = _item(1, "日間部學生獎學金")
    energy_item = _item(2, "電力與能源優秀學生獎學金")
    items = [day_item, energy_item]
    details = {
        day_item.source_url: "限日間部學生申請。",
        energy_item.source_url: "大專在校生，電子工程相關科系可申請。",
    }
    sent_messages: list[str] = []
    service, _ = _service(tmp_path, items, details, sent_messages)

    result = service.run(dry_run=False)

    assert result.notified_count == 1
    assert len(sent_messages) == 1
    assert energy_item.title in sent_messages[0]
    assert energy_item.source_url in sent_messages[0]
    assert "符合原因" in sent_messages[0]
    assert day_item.title not in sent_messages[0]


def test_profile_change_re_evaluates_existing_item(tmp_path: Path) -> None:
    item = _item(1, "電力工程獎學金")
    sent_messages: list[str] = []
    service, repository = _service(
        tmp_path,
        [item],
        {item.source_url: "申請對象限碩士生。"},
        sent_messages,
    )
    first = service.run(dry_run=True)
    assert first.pending_items == []

    eligible_profile = StudentProfile(
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
        research_keywords=("電力工程",),
    )
    second_service = ScholarshipService(
        FakeCollector([item]),
        repository,
        sent_messages.append,
        include_keywords=("獎學金",),
        summary_batch_size=5,
        detail_fetcher=FakeDetailFetcher(
            {item.source_url: "大專院校學生可申請電力工程獎學金。"}
        ),
        evaluator=EligibilityEvaluator(),
        profile=eligible_profile,
        notify_review_items=False,
    )

    second = second_service.run(dry_run=True)

    assert [candidate.title for candidate in second.pending_items] == [item.title]
