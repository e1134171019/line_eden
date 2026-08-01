# -*- coding: utf-8 -*-

from pathlib import Path
from typing import Callable

import pytest

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship
from src.notifiers.notification_dispatcher import (
    CallableNotificationChannel,
    NotificationFanout,
)
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ScholarshipService

TEST_SUMMARY_BATCH_SIZE = 5


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
    service = ScholarshipService(
        FakeCollector(items),
        repository,
        NotificationFanout((CallableNotificationChannel("test", notifier),)),
        summary_batch_size=TEST_SUMMARY_BATCH_SIZE,
    )
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
        NotificationFanout(tuple()),
        summary_batch_size=TEST_SUMMARY_BATCH_SIZE,
    )
    result = next_service.run(dry_run=True)

    assert [item.content_hash for item in result.pending_items] == [new_item.content_hash]


# 驗證同一則摘要中的每筆公告都有自己的連結。
def test_service_summary_contains_each_item_link(tmp_path: Path) -> None:
    sent_messages: list[str] = []
    items = [_build_item(1), _build_item(2), _build_item(3)]
    service, repository = _build_service(tmp_path, items, sent_messages.append)

    result = service.run(dry_run=False)

    assert result.notified_count == 3
    assert len(sent_messages) == 1
    for item in items:
        assert item.title in sent_messages[0]
        assert item.source_url in sent_messages[0]
    assert repository.list_pending() == []


# 驗證超過單則上限時會分批，且每批公告都有連結。
def test_service_splits_large_summary_into_batches(tmp_path: Path) -> None:
    sent_messages: list[str] = []
    items = [_build_item(index) for index in range(1, 7)]
    service, repository = _build_service(tmp_path, items, sent_messages.append)

    result = service.run(dry_run=False)

    assert result.notified_count == 6
    assert len(sent_messages) == 2
    assert "https://example.com/6" in sent_messages[0]
    assert "https://example.com/1" not in sent_messages[0]
    assert "https://example.com/1" in sent_messages[1]
    assert repository.list_pending() == []


# 驗證 LINE 失敗時，失敗批次與後續公告仍維持待通知。
def test_service_batch_failure_keeps_unsent_items_pending(tmp_path: Path) -> None:
    items = [_build_item(index) for index in range(1, 7)]
    sent_messages: list[str] = []

    # 第二批推播時模擬 LINE API 發生錯誤。
    def failed_second_batch(message: str) -> None:
        sent_messages.append(message)
        if len(sent_messages) == 2:
            raise RuntimeError("LINE API error")

    service, repository = _build_service(tmp_path, items, failed_second_batch)

    with pytest.raises(RuntimeError, match="LINE API error"):
        service.run(dry_run=False)

    pending_urls = [item.source_url for item in repository.list_pending()]
    assert pending_urls == ["https://example.com/1"]


# 多管道部分成功時，重試只補送失敗管道，不重複已成功的通知。
def test_service_retries_only_failed_notification_channel(tmp_path: Path) -> None:
    item = _build_item(1)
    line_messages: list[str] = []
    webhook_messages: list[str] = []
    has_failed_once = False

    def flaky_webhook(message: str) -> None:
        nonlocal has_failed_once
        webhook_messages.append(message)
        if not has_failed_once:
            has_failed_once = True
            raise RuntimeError("Webhook unavailable")

    repository = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    dispatcher = NotificationFanout(
        (
            CallableNotificationChannel("line", line_messages.append),
            CallableNotificationChannel("webhook", flaky_webhook),
        )
    )
    service = ScholarshipService(
        FakeCollector([item]),
        repository,
        dispatcher,
        summary_batch_size=TEST_SUMMARY_BATCH_SIZE,
    )

    with pytest.raises(RuntimeError, match="Webhook unavailable"):
        service.run(dry_run=False)
    assert len(repository.list_pending()) == 1

    retried = service.run(dry_run=False)

    assert retried.notified_count == 1
    assert len(line_messages) == 1
    assert len(webhook_messages) == 2
    assert repository.list_pending() == []


# 專用 Collector 已確認來源範圍，非標準方案名稱仍必須進入正式流程。
def test_live_preserves_collector_scoped_notice_without_title_keywords(
    tmp_path: Path,
) -> None:
    scholarship = Scholarship.from_raw(
        "tun-program-foxconn-scholarship-whale",
        "鴻海獎學鯨",
        "2026-07-01",
        "https://example.com/foxconn",
    )
    sent_messages: list[str] = []
    service, repository = _build_service(tmp_path, [scholarship], sent_messages.append)

    result = service.run(dry_run=False)

    assert scholarship.category == "other"
    assert result.collected == [scholarship]
    assert result.notified_count == 1
    assert len(sent_messages) == 1
    assert repository.list_pending() == []
    assert service.source_summary_lines() == [
        "入庫資料守恆：輸入 1 = 唯一公告 1 + 輸入內重複 0；"
        "唯一公告 = 新增 1 + 既有更新 0",
    ]


# 驗證同批重複 identity 不會在入庫階段無聲消失。
def test_service_reports_duplicate_identity_before_repository(tmp_path: Path) -> None:
    item = _build_item(1)
    service, _ = _build_service(tmp_path, [item, item], lambda _: None)

    service.run(dry_run=True)

    assert service.discovery_result is not None
    assert service.discovery_result.input_count == 2
    assert service.discovery_result.unique_count == 1
    assert service.discovery_result.duplicate_input_count == 1
    assert service.discovery_result.inserted_count == 1
