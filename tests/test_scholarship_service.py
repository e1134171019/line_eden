# -*- coding: utf-8 -*-

from pathlib import Path
from typing import Callable

import pytest

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ScholarshipService


class FakeCollector(BaseCollector):
    """回傳測試指定公告的蒐集器。"""

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


# 建立測試服務與暫存資料庫。
def _build_service(
    tmp_path: Path,
    items: list[Scholarship],
    notifier: Callable[[str], None],
) -> tuple[ScholarshipService, ScholarshipRepository]:
    repository = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    service = ScholarshipService(FakeCollector(items), repository, notifier)
    return service, repository


# 驗證重複 dry-run 仍保留相同待通知公告且不通知。
def test_service_repeated_dry_run_keeps_pending(tmp_path: Path) -> None:
    sent_messages: list[str] = []
    service, repository = _build_service(
        tmp_path,
        [_build_item(1), _build_item(2)],
        sent_messages.append,
    )

    first_result = service.run(dry_run=True)
    second_result = service.run(dry_run=True)

    assert len(first_result.pending_items) == 2
    assert len(second_result.pending_items) == 2
    assert len(repository.list_pending()) == 2
    assert sent_messages == []


# 驗證初始化基準後不再有待通知歷史公告。
def test_service_initialize_baseline_clears_pending(tmp_path: Path) -> None:
    service, repository = _build_service(
        tmp_path,
        [_build_item(1), _build_item(2), _build_item(3)],
        lambda _: None,
    )

    result = service.initialize_baseline()

    assert result.baseline_count == 3
    assert result.pending_items == []
    assert repository.list_pending() == []


# 驗證基準建立後新增公告會成為唯一待通知資料。
def test_service_new_item_after_baseline_is_pending(tmp_path: Path) -> None:
    old_item = _build_item(1)
    service, repository = _build_service(tmp_path, [old_item], lambda _: None)
    service.initialize_baseline()

    new_item = _build_item(2)
    next_service = ScholarshipService(
        FakeCollector([old_item, new_item]),
        repository,
        lambda _: None,
    )
    result = next_service.run(dry_run=True)

    assert [item.content_hash for item in result.pending_items] == [new_item.content_hash]


# 驗證 LINE 成功後才移除待通知狀態。
def test_service_live_success_marks_notified(tmp_path: Path) -> None:
    sent_messages: list[str] = []
    item = _build_item(1)
    service, repository = _build_service(tmp_path, [item], sent_messages.append)

    result = service.run(dry_run=False)

    assert result.notified_count == 1
    assert len(sent_messages) == 1
    assert repository.list_pending() == []


# 驗證 LINE 失敗時公告仍維持待通知。
def test_service_live_failure_keeps_pending(tmp_path: Path) -> None:
    item = _build_item(1)

    # 模擬外部 LINE API 發生錯誤。
    def failed_notifier(_: str) -> None:
        raise RuntimeError("LINE API error")

    service, repository = _build_service(tmp_path, [item], failed_notifier)

    with pytest.raises(RuntimeError, match="LINE API error"):
        service.run(dry_run=False)

    assert [pending.content_hash for pending in repository.list_pending()] == [item.content_hash]


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
    repository = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    service = ScholarshipService(
        FakeCollector([keep_item, drop_item]),
        repository,
        lambda _: None,
        include_keywords=("獎學金", "助學金"),
    )

    result = service.run(dry_run=True)

    assert len(result.collected) == 1
    assert len(result.pending_items) == 1
    assert result.collected[0].title == "2026 優秀學生獎學金"
