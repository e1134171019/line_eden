# -*- coding: utf-8 -*-

from typing import Protocol

from src.catalogs.additional_source_catalog import (
    AdditionalScholarshipSource,
    AdditionalSourceAdapterId,
)
from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
)
from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectionMode


class AdditionalSourceAdapterRegistryProtocol(Protocol):
    """additional source collector 建立介面。"""

    def build(
        self,
        config: AdditionalScholarshipSource,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode,
        max_pages: int,
    ) -> BaseCollector: ...


class AdditionalSourceAdapterRegistry:
    """依來源契約的 adapter_id 建立對應 collector。"""

    # 依 adapter_id 建立 collector；未知策略採 fail closed。
    def build(
        self,
        config: AdditionalScholarshipSource,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode,
        max_pages: int,
    ) -> BaseCollector:
        if config.adapter_id is AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST:
            return AdditionalScholarshipSourceCollector(
                config,
                timeout_seconds,
                user_agent,
                collection_mode,
                max_pages,
            )
        raise ValueError(f"未知 additional source adapter：{config.adapter_id}")
