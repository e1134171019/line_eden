# -*- coding: utf-8 -*-

from typing import Protocol

from src.catalogs.additional_source_catalog import (
    BROAD_SCHOLARSHIP_PORTALS,
    OFFICIAL_ADDITIONAL_SOURCES,
    AdditionalScholarshipSource,
)


class AdditionalSourceRegistryProtocol(Protocol):
    """已批准 additional source 分組查詢介面。"""

    def official_sources(self) -> tuple[AdditionalScholarshipSource, ...]: ...

    def broad_sources(self) -> tuple[AdditionalScholarshipSource, ...]: ...


class AdditionalSourceRegistry:
    """提供已審查通過的 additional source 契約。"""

    # 回傳官方或方案型 additional sources。
    def official_sources(self) -> tuple[AdditionalScholarshipSource, ...]:
        return OFFICIAL_ADDITIONAL_SOURCES

    # 回傳跨校校外獎助學金發現入口。
    def broad_sources(self) -> tuple[AdditionalScholarshipSource, ...]:
        return BROAD_SCHOLARSHIP_PORTALS
