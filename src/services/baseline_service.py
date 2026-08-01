# -*- coding: utf-8 -*-

from src.collectors.base_collector import BaseCollector
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.scholarship_service import ServiceResult


class BaselineService:
    """只負責蒐集、去重與建立歷史基準，不包含資格判斷或通知。"""

    def __init__(
        self,
        collector: BaseCollector,
        repository: ScholarshipRepository,
    ) -> None:
        self.collector = collector
        self.repository = repository

    def initialize_baseline(self) -> ServiceResult:
        collected = self.collector.collect()
        self.repository.discover(collected)
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
