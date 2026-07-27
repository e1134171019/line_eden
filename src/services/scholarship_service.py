# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Callable

from src.collectors.base_collector import BaseCollector
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
    """協調蒐集、去重與通知流程。"""

    # 注入 Collector、Repository 與通知函式。
    def __init__(
        self,
        collector: BaseCollector,
        repository: ScholarshipRepository,
        notifier: Callable[[str], None],
        include_keywords: tuple[str, ...] | None = None,
    ) -> None:
        self.collector = collector
        self.repository = repository
        self.notifier = notifier
        self.include_keywords = include_keywords or tuple()

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
        filtered: list[Scholarship] = []
        for item in collected:
            if any(keyword in item.title for keyword in self.include_keywords):
                filtered.append(item)
        return filtered

    # 處理正式模式的儲存與通知流程。
    def _run_live_mode(self, collected: list[Scholarship], pending_items: list[Scholarship]) -> ServiceResult:
        if not pending_items:
            return ServiceResult(collected, [], 0, 0, "沒有待通知公告。")
        return self._notify_each_item(collected, pending_items)

    # 對每筆新公告逐一通知，成功後才標記已通知。
    def _notify_each_item(self, collected: list[Scholarship], pending_items: list[Scholarship]) -> ServiceResult:
        notified_count = 0
        for item in pending_items:
            self.notifier(self._build_single_message(item))
            self.repository.mark_notified([item.content_hash])
            notified_count += 1
        return ServiceResult(collected, pending_items, notified_count, 0, "已送出待通知公告。")

    # 建立單筆公告訊息。
    def _build_single_message(self, item: Scholarship) -> str:
        lines = [
            "【獎學金新公告】",
            f"分類：{item.category}",
            f"日期：{item.published_date}",
            f"標題：{item.title}",
            f"連結：{item.source_url}",
        ]
        return "\n".join(lines)
