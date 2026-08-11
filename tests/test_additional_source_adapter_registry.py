# -*- coding: utf-8 -*-

from dataclasses import replace
from typing import cast

import pytest

from src.catalogs.additional_source_catalog import (
    AdditionalScholarshipSource,
    AdditionalSourceAdapterId,
)
from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
)
from src.collectors.additional_source_adapter_registry import (
    AdditionalSourceAdapterRegistry,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.wordpress_archive_scholarship_collector import (
    WordPressArchiveScholarshipCollector,
)


def _config(**overrides: object) -> AdditionalScholarshipSource:
    values: dict[str, object] = {
        "source_id": "test-source",
        "display_name": "測試來源",
        "entry_url": "https://example.com/scholarships",
        "allowed_hosts": ("example.com",),
        "review_reason": "測試來源。",
        "adapter_id": AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST,
    }
    values.update(overrides)
    return AdditionalScholarshipSource(**values)  # type: ignore[arg-type]


def test_additional_source_requires_explicit_adapter_id() -> None:
    with pytest.raises(TypeError, match="adapter_id"):
        AdditionalScholarshipSource(  # type: ignore[call-arg]
            source_id="test-source",
            display_name="測試來源",
            entry_url="https://example.com/scholarships",
            allowed_hosts=("example.com",),
            review_reason="測試來源。",
        )


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


def test_registry_builds_wordpress_archive_collector() -> None:
    registry = AdditionalSourceAdapterRegistry()
    wordpress_adapter = cast(AdditionalSourceAdapterId, "wordpress_archive")
    config = replace(_config(), adapter_id=wordpress_adapter)

    collector = registry.build(
        config,
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        20,
    )

    assert isinstance(collector, WordPressArchiveScholarshipCollector)
    assert collector.config.source_id == "test-source"


def test_registry_fails_closed_for_unknown_adapter() -> None:
    registry = AdditionalSourceAdapterRegistry()
    unknown_adapter = cast(AdditionalSourceAdapterId, "unknown-adapter")
    config = replace(_config(), adapter_id=unknown_adapter)

    with pytest.raises(ValueError, match="unknown-adapter"):
        registry.build(
            config,
            10.0,
            "test-agent",
            CollectionMode.INCREMENTAL,
            20,
        )
