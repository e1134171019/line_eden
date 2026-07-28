# -*- coding: utf-8 -*-

from pathlib import Path

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.baseline_service import BaselineService


class FakeCollector(BaseCollector):
    """回傳固定公告，供基準服務測試。"""

    def __init__(self, items: list[Scholarship]) -> None:
        self.items = items

    def collect(self) -> list[Scholarship]:
        return self.items


def _item(index: int, title: str) -> Scholarship:
    return Scholarship.from_raw(
        "fixture",
        title,
        f"2026-07-{index:02d}",
        f"https://example.com/{index}",
    )


def _service(
    tmp_path: Path,
    items: list[Scholarship],
    keywords: tuple[str, ...] | None = None,
) -> tuple[BaselineService, ScholarshipRepository]:
    repository = ScholarshipRepository(tmp_path / "scholarships.db")
    service = BaselineService(FakeCollector(items), repository, keywords)
    return service, repository


# 基準服務只建立歷史基準，不產生待通知資料。
def test_baseline_service_marks_current_items_without_notification_state(tmp_path: Path) -> None:
    items = [_item(1, "能源獎學金"), _item(2, "學生助學金")]
    service, repository = _service(tmp_path, items)

    result = service.initialize_baseline()

    assert result.baseline_count == 2
    assert result.notified_count == 0
    assert result.pending_items == []
    assert repository.list_pending() == []


# 關鍵字過濾應在 discover 與 baseline 前完成。
def test_baseline_service_filters_irrelevant_announcements(tmp_path: Path) -> None:
    keep = _item(1, "能源獎學金")
    drop = _item(2, "一般行政公告")
    service, repository = _service(tmp_path, [keep, drop], ("獎學金", "助學金"))

    result = service.initialize_baseline()

    assert [item.content_hash for item in result.collected] == [keep.content_hash]
    assert result.baseline_count == 1
    assert repository.list_pending() == []
