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


def _item(title: str, index: int) -> Scholarship:
    return Scholarship.from_raw(
        "lhu",
        title,
        f"2026-07-{index:02d}",
        f"https://example.com/{index}",
    )


def test_baseline_service_does_not_require_profile_or_notifier(tmp_path: Path) -> None:
    keep = _item("能源獎學金", 1)
    drop = _item("一般行政公告", 2)
    repository = ScholarshipRepository(tmp_path / "data" / "scholarships.db")
    service = BaselineService(
        FakeCollector([keep, drop]),
        repository,
        include_keywords=("獎學金",),
    )

    result = service.initialize_baseline()

    assert result.baseline_count == 1
    assert result.pending_items == []
    assert [item.title for item in result.collected] == [keep.title]
