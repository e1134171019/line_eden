# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    AdditionalScholarshipSource,
    AdditionalSourceAdapterId,
)
from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.expanded_scholarship_collector import ExpandedScholarshipCollector
from src.models.scholarship import Scholarship


class FakeCollector(BaseCollector):
    """測試用 collector。"""

    def collect(self) -> list[Scholarship]:
        return []


class RecordingAdapterRegistry:
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


class RecordingSourceRegistry:
    """測試用來源分組 registry。"""

    def __init__(
        self,
        official: tuple[AdditionalScholarshipSource, ...],
        broad: tuple[AdditionalScholarshipSource, ...],
    ) -> None:
        self.official = official
        self.broad = broad

    def official_sources(self) -> tuple[AdditionalScholarshipSource, ...]:
        return self.official

    def broad_sources(self) -> tuple[AdditionalScholarshipSource, ...]:
        return self.broad


def _config(source_id: str) -> AdditionalScholarshipSource:
    return AdditionalScholarshipSource(
        source_id=source_id,
        display_name=f"{source_id} 測試來源",
        entry_url=f"https://example.com/{source_id}",
        allowed_hosts=("example.com",),
        review_reason="測試來源。",
        adapter_id=AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST,
    )


def test_expanded_collector_routes_additional_source_through_adapter_registry() -> None:
    registry = RecordingAdapterRegistry()
    collector = ExpandedScholarshipCollector(
        "https://example.com",
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        20,
        additional_source_adapter_registry=registry,
    )

    built = collector._additional_collector(_config("test-source"))

    assert built is registry.collector
    assert registry.source_ids == ["test-source"]


def test_expanded_collector_loads_groups_from_source_registry() -> None:
    official = _config("official-source")
    broad = _config("broad-source")
    source_registry = RecordingSourceRegistry((official,), (broad,))
    adapter_registry = RecordingAdapterRegistry()
    collector = ExpandedScholarshipCollector(
        "https://example.com",
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        20,
        additional_source_registry=source_registry,
        additional_source_adapter_registry=adapter_registry,
    )

    official_collectors, broad_collectors = collector._additional_collectors()

    assert official_collectors == [adapter_registry.collector]
    assert broad_collectors == [adapter_registry.collector]
    assert adapter_registry.source_ids == ["official-source", "broad-source"]
