# -*- coding: utf-8 -*-

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ServiceResult


class BaselineService:
    """只負責蒐集與建立歷史基準，不持有 profile、evaluator 或 notifier。"""

    def __init__(
        self,
        collector: BaseCollector,
        repository: ScholarshipRepository,
        include_keywords: tuple[str, ...] | None,
    ) -> None:
        self.collector = collector
        self.repository = repository
        self.include_keywords = include_keywords or tuple()

    def initialize_baseline(self) -> ServiceResult:
        collected = self._filter_collected(self.collector.collect())
        self.repository.discover(collected)
        baseline_count = self.repository.mark_baseline(
            [item.content_hash for item in collected]
        )
        pending_items = self.repository.list_pending()
        return ServiceResult(
            collected,
            pending_items,
            0,
            baseline_count,
            f"已設定 {baseline_count} 筆歷史基準。",
        )

    def _filter_collected(self, collected: list[Scholarship]) -> list[Scholarship]:
        if not self.include_keywords:
            return collected
        return [
            item
            for item in collected
            if any(keyword in item.title for keyword in self.include_keywords)
        ]
