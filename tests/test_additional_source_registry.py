# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    BROAD_SCHOLARSHIP_PORTALS,
    OFFICIAL_ADDITIONAL_SOURCES,
)
from src.catalogs.additional_source_registry import AdditionalSourceRegistry


def test_source_registry_exposes_approved_source_groups() -> None:
    registry = AdditionalSourceRegistry()

    assert registry.official_sources() == OFFICIAL_ADDITIONAL_SOURCES
    assert registry.broad_sources() == BROAD_SCHOLARSHIP_PORTALS
