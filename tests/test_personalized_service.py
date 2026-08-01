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
    """依公告網址回傳固定內文。"""

    # 初始化網址與內文對照。
    def __init__(self, details: dict[str, str]) -> None:
        self.details = details

    # 回傳指定公告的測試內文。
    def fetch_text(self, scholarship: Scholarship) -> str:
        return self.details[scholarship.source_url]


# 建立匿名進修部電子工程學生背景。
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


# 建立測試公告。
def _item(index: int, title: str) -> Scholarship:
    return Scholarship.from_raw(
        "lhu",
        title,
        f"2026-07-{index:02d}",
        f"https://example.com/{index}",
    )


# 建立含個人化資格判斷的服務。
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


# 驗證 dry-run 只列出明確適合公告，不推播不適合或待確認資料。
def test_personalized_dry_run_only_returns_eligible(tmp_path: Path) -> None:
    day_item = _item(1, "日間部學生獎學金")
    energy_item = _item(2, "電力與能源優秀學生獎學金")
    unknown_item = _item(3, "希望獎助學金")
    items = [day_item, energy_item, unknown_item]
    details = {
        day_item.source_url: "限日間部學生申請。",
        energy_item.source_url: "電子工程相關科系，學業平均 80 分以上。",
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


# 驗證正式模式只傳送適合公告並在訊息中列出符合原因。
def test_live_mode_only_sends_eligible_item(tmp_path: Path) -> None:
    day_item = _item(1, "日間部學生獎學金")
    energy_item = _item(2, "電力與能源優秀學生獎學金")
    items = [day_item, energy_item]
    details = {
        day_item.source_url: "限日間部學生申請。",
        energy_item.source_url: "大專在校生，電子工程相關科系可申請。",
    }
    sent_messages: list[str] = []
    service, repository = _service(tmp_path, items, details, sent_messages)

    result = service.run(dry_run=False)

    assert result.notified_count == 1
    assert len(sent_messages) == 1
    assert energy_item.title in sent_messages[0]
    assert energy_item.source_url in sent_messages[0]
    assert "符合原因" in sent_messages[0]
    assert day_item.title not in sent_messages[0]
    assert repository.list_notifiable(_profile().fingerprint(), False) == []


# 驗證公告內文讀取失敗時採保守待確認，不會推播。
def test_detail_failure_is_not_sent(tmp_path: Path) -> None:
    item = _item(1, "未知條件獎學金")
    sent_messages: list[str] = []
    service, _ = _service(tmp_path, [item], {}, sent_messages)

    result = service.run(dry_run=False)

    assert result.notified_count == 0
    assert result.review_count == 1
    assert sent_messages == []


# 同一公告只有實質正文變更才重開評估與通知，純空白調整不重送。
def test_content_revision_re_evaluates_and_notifies_again(tmp_path: Path) -> None:
    item = _item(1, "能源工程學生獎學金")
    details = {
        item.source_url: "大專在校生，電子工程相關科系可申請。",
    }
    sent_messages: list[str] = []
    service, _ = _service(tmp_path, [item], details, sent_messages)

    first = service.run(dry_run=False)
    details[item.source_url] = "  大專在校生，電子工程相關科系可申請。  "
    formatting_only = service.run(dry_run=False)
    details[item.source_url] = "大專在校生，電子工程相關科系可申請，學業平均須達 80 分。"
    changed = service.run(dry_run=False)

    assert first.notified_count == 1
    assert formatting_only.notified_count == 0
    assert changed.notified_count == 1
    assert len(sent_messages) == 2


# 已通知的舊資料第一次建立 revision 基準時不得再次推播。
def test_existing_notification_initializes_revision_without_resending(
    tmp_path: Path,
) -> None:
    item = _item(1, "能源工程學生獎學金")
    details = {item.source_url: "大專在校生，電子工程相關科系可申請。"}
    sent_messages: list[str] = []
    service, repository = _service(tmp_path, [item], details, sent_messages)
    repository.discover([item])
    repository.mark_eligibility(
        item.content_hash,
        "eligible",
        "既有符合結果",
        _profile().fingerprint(),
    )
    repository.mark_notified([item.content_hash])

    result = service.run(dry_run=False)

    assert result.notified_count == 0
    assert sent_messages == []
