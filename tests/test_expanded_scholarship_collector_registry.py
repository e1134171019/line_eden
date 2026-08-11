# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import AdditionalScholarshipSource
from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.expanded_scholarship_collector import ExpandedScholarshipCollector
from src.models.scholarship import Scholarship


class FakeCollector(BaseCollector):
    """測試用 collector。"""

    def collect(self) -> list[Scholarship]:
        return []


class RecordingRegistry:
    """記錄 ExpandedScholarshipCollector 是否委派來源建立。"""

    def __init__(self) -> None:
        self.collector = FakeCollector()
        self.source_ids: list[str] = []

    def build(
        self,
        config: AdditionalScholarshipSource,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode,
        max_pages: int,
    ) -> BaseCollector:
        self.source_ids.append(config.source_id)
        assert timeout_seconds == 10.0
        assert user_agent == "test-agent"
        assert collection_mode is CollectionMode.INCREMENTAL
        assert max_pages == 20
        return self.collector


def test_expanded_collector_routes_additional_source_through_registry() -> None:
    registry = RecordingRegistry()
    collector = ExpandedScholarshipCollector(
        "https://example.com",
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        20,
        additional_source_adapter_registry=registry,
    )
    config = AdditionalScholarshipSource(
        source_id="test-source",
        display_name="測試來源",
        entry_url="https://example.com/scholarships",
        allowed_hosts=("example.com",),
        review_reason="測試來源。",
        adapter_id="generic_anchor_list",
    )

    built = collector._additional_collector(config)

    assert built is registry.collector
    assert registry.source_ids == ["test-source"]
