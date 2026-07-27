# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Callable

from src.collectors.base_collector import BaseCollector
from src.formatters.scholarship_message_formatter import (
    build_summary_message,
    split_scholarships,
)
from src.models.scholarship import Scholarship
from src.repositories.scholarship_repository import ScholarshipRepository


@dataclass(frozen=True)
class ServiceResult:
    collected: list[Scholarship]
    pending_items: list[Scholarship]
    notified_count: int
    baseline_count: int
    message: str


class ScholarshipService:
    """協調蒐集、去重與 LINE 摘要通知流程。"""

    # 注入 Collector、Repository、通知函式與摘要批次大小。
    def __init__(
        self,
        collector: BaseCollector,
        repository: ScholarshipRepository,
        notifier: Callable[[str], None],
        include_keywords: tuple[str, ...] | None,
        summary_batch_size: int,
    ) -> None:
        self.collector = collector
        self.repository = repository
        self.notifier = notifier
        self.include_keywords = include_keywords or tuple()
        self.summary_batch_size = summary_batch_size

    # 執行蒐集流程，依模式決定是否通知與寫入通知狀態。
    def run(self, dry_run: bool) -> ServiceResult:
        collected = self._collect_and_discover()
        pending_items = self.repository.list_pending()
        if dry_run:
            return ServiceResult(collected, pending_items, 0, 0, "dry-run，不會傳送 LINE。")
        return self._run_live_mode(collected, pending_items)

    # 執行首次基準化，不推播僅標記 baseline。
    def initialize_baseline(self) -> ServiceResult:
        collected = self._collect_and_discover()
        hashes = [item.content_hash for item in collected]
        baseline_count = self.repository.mark_baseline(hashes)
        pending_items = self.repository.list_pending()
        return ServiceResult(
            collected,
            pending_items,
            0,
            baseline_count,
            f"已設定 {baseline_count} 筆歷史基準。",
        )

    # 蒐集公告並寫入 discovered 資料。
    def _collect_and_discover(self) -> list[Scholarship]:
        collected = self._filter_collected(self.collector.collect())
        self.repository.discover(collected)
        return collected

    # 依關鍵字過濾公告，降低非目標訊息噪音。
    def _filter_collected(self, collected: list[Scholarship]) -> list[Scholarship]:
        if not self.include_keywords:
            return collected
        return [
            item
            for item in collected
            if any(keyword in item.title for keyword in self.include_keywords)
        ]

    # 處理正式模式的摘要通知流程。
    def _run_live_mode(
        self,
        collected: list[Scholarship],
        pending_items: list[Scholarship],
    ) -> ServiceResult:
        if not pending_items:
            return ServiceResult(collected, [], 0, 0, "沒有待通知公告。")
        return self._notify_batches(collected, pending_items)

    # 分批推播摘要，成功後才標記該批公告為已通知。
    def _notify_batches(
        self,
        collected: list[Scholarship],
        pending_items: list[Scholarship],
    ) -> ServiceResult:
        batches = split_scholarships(pending_items, self.summary_batch_size)
        notified_count = self._send_batches(batches)
        message = f"已送出 {len(batches)} 則摘要，共通知 {notified_count} 筆公告。"
        return ServiceResult(collected, pending_items, notified_count, 0, message)

    # 逐批送出摘要並更新成功批次的 notified_at。
    def _send_batches(self, batches: list[list[Scholarship]]) -> int:
        notified_count = 0
        for index, batch in enumerate(batches, start=1):
            message = build_summary_message(batch, index, len(batches))
            self.notifier(message)
            hashes = [item.content_hash for item in batch]
            notified_count += self.repository.mark_notified(hashes)
        return notified_count
