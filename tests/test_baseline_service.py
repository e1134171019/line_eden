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
) -> tuple[BaselineService, ScholarshipRepository]:
    repository = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    return BaselineService(FakeCollector(items), repository), repository


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


def test_baseline_preserves_notice_without_standard_title_keywords(tmp_path: Path) -> None:
    scholarship = _item(1, "鴻海獎學鯨")
    service, repository = _service(tmp_path, [scholarship])

    result = service.initialize_baseline()

    assert scholarship.category == "other"
    assert result.collected == [scholarship]
    assert result.baseline_count == 1
    assert repository.list_pending() == []
