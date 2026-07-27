# -*- coding: utf-8 -*-

from pathlib import Path

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ScholarshipService


class FakeCollector(BaseCollector):
    # 初始化測試用固定公告資料。
    def __init__(self, items: list[Scholarship]) -> None:
        self.items = items

    # 回傳預先指定的公告清單。
    def collect(self) -> list[Scholarship]:
        return self.items


# 建立測試用 Scholarship 物件。
def _build_item(index: int) -> Scholarship:
    return Scholarship.from_raw(
        "lhu",
        f"公告 {index}",
        f"2026-07-{index:02d}",
        f"https://example.com/{index}",
    )


# 驗證 dry-run 僅顯示結果且不觸發通知或寫入。
def test_service_dry_run_no_notify_no_write(tmp_path: Path) -> None:
    items = [_build_item(1), _build_item(2)]
    collector = FakeCollector(items)
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    sent_messages: list[str] = []
    service = ScholarshipService(collector, repo, sent_messages.append)

    result = service.run(dry_run=True)

    assert len(result.collected) == 2
    assert len(result.new_items) == 2
    assert repo.is_empty()
    assert sent_messages == []


# 驗證首次大量新公告只送一則摘要通知。
def test_service_first_run_send_summary_once(tmp_path: Path) -> None:
    items = [_build_item(1), _build_item(2), _build_item(3)]
    collector = FakeCollector(items)
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    sent_messages: list[str] = []
    service = ScholarshipService(collector, repo, sent_messages.append)

    result = service.run(dry_run=False)

    assert result.notified_count == 1
    assert len(sent_messages) == 1
    assert "首次同步摘要" in sent_messages[0]


# 驗證非首次執行只通知新進公告。
def test_service_notify_only_new_items(tmp_path: Path) -> None:
    old_item = _build_item(1)
    new_item = _build_item(2)
    first_collector = FakeCollector([old_item])
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    first_service = ScholarshipService(first_collector, repo, lambda _: None)
    first_service.run(dry_run=False)

    sent_messages: list[str] = []
    second_collector = FakeCollector([old_item, new_item])
    second_service = ScholarshipService(second_collector, repo, sent_messages.append)

    result = second_service.run(dry_run=False)

    assert result.notified_count == 1
    assert len(result.new_items) == 1
    assert "公告 2" in sent_messages[0]


# 驗證關鍵字過濾只保留目標公告。
def test_service_filter_by_keywords(tmp_path: Path) -> None:
    keep_item = Scholarship.from_raw(
        "lhu",
        "2026 優秀學生獎學金",
        "2026-07-01",
        "https://example.com/keep",
    )
    drop_item = Scholarship.from_raw(
        "lhu",
        "教務處一般行政公告",
        "2026-07-01",
        "https://example.com/drop",
    )
    collector = FakeCollector([keep_item, drop_item])
    repo = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    service = ScholarshipService(
        collector,
        repo,
        lambda _: None,
        include_keywords=("獎學金", "助學金"),
    )

    result = service.run(dry_run=True)

    assert len(result.collected) == 1
    assert len(result.new_items) == 1
    assert result.collected[0].title == "2026 優秀學生獎學金"
