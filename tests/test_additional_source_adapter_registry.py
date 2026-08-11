# -*- coding: utf-8 -*-

from dataclasses import replace

import pytest

from src.catalogs.additional_source_catalog import AdditionalScholarshipSource
from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
)
from src.collectors.additional_source_adapter_registry import (
    AdditionalSourceAdapterRegistry,
)
from src.collectors.collection_diagnostics import CollectionMode


def _config(**overrides: object) -> AdditionalScholarshipSource:
    values: dict[str, object] = {
        "source_id": "test-source",
        "display_name": "測試來源",
        "entry_url": "https://example.com/scholarships",
        "allowed_hosts": ("example.com",),
        "review_reason": "測試來源。",
    }
    values.update(overrides)
    return AdditionalScholarshipSource(**values)  # type: ignore[arg-type]


def test_additional_source_defaults_to_generic_anchor_adapter() -> None:
    assert _config().adapter_id == "generic_anchor_list"


def test_registry_builds_generic_anchor_collector() -> None:
    registry = AdditionalSourceAdapterRegistry()

    collector = registry.build(
        _config(),
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        20,
    )

    assert isinstance(collector, AdditionalScholarshipSourceCollector)
    assert collector.config.source_id == "test-source"


def test_registry_fails_closed_for_unknown_adapter() -> None:
    registry = AdditionalSourceAdapterRegistry()
    config = replace(_config(), adapter_id="unknown-adapter")

    with pytest.raises(ValueError, match="unknown-adapter"):
        registry.build(
            config,
            10.0,
            "test-agent",
            CollectionMode.INCREMENTAL,
            20,
        )
