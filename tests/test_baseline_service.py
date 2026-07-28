# -*- coding: utf-8 -*-

from pathlib import Path

from src.collectors.base_collector import BaseCollector
from src.models.scholarship import Scholarship
from src.repositories.scholarship_repository import ScholarshipRepository
from src.services.baseline_service import BaselineService


class FakeCollector(BaseCollector):
    def __init__(self, items: list[Scholarship]) -> None:
        self.items = items

    def collect(self) -> list[Scholarship]:
        return self.items


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
    keywords: tuple[str, ...] | None = None,
) -> tuple[BaselineService, ScholarshipRepository]:
    repository = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    return BaselineService(FakeCollector(items), repository, keywords), repository


def test_baseline_service_marks_current_items_without_notification_dependencies(
    tmp_path: Path,
) -> None:
    items = [_item(1, "能源獎學金"), _item(2, "助學金公告")]
    service, repository = _service(tmp_path, items)

    result = service.initialize_baseline()

    assert result.baseline_count == 2
    assert result.notified_count == 0
    assert result.pending_items == []
    assert repository.list_pending() == []


def test_baseline_service_applies_same_title_filter_as_full_service(tmp_path: Path) -> None:
    keep = _item(1, "能源獎學金")
    drop = _item(2, "一般行政公告")
    service, repository = _service(tmp_path, [keep, drop], ("獎學金", "助學金"))

    result = service.initialize_baseline()

    assert result.collected == [keep]
    assert result.baseline_count == 1
    assert repository.list_pending() == []
