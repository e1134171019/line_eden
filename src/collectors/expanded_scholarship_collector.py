# -*- coding: utf-8 -*-

from collections import Counter

from src.catalogs.additional_source_catalog import (
    BROAD_SCHOLARSHIP_PORTALS,
    OFFICIAL_ADDITIONAL_SOURCES,
    AdditionalScholarshipSource,
)
from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
)
from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.decision_safe_tun_program_watch_collector import (
    DecisionSafeTunProgramWatchCollector,
)
from src.collectors.helpdreams_collector import HelpDreamsCollector
from src.collectors.indigenous_grant_collector import IndigenousGrantCollector
from src.collectors.lhu_collector import (
    LhuCollector,
    _HELPDREAMS_GOVERNMENT_URL,
    _HELPDREAMS_PRIVATE_URL,
    _INDIGENOUS_GRANTS_URL,
    _LhuOnlyCollector,
    _XINZHUANG_AWARDS_URL,
)
from src.collectors.moe_overseas_collector import MoeOverseasCollector
from src.collectors.multi_source_collector import MultiSourceCollector
from src.collectors.tun_program_watch_collector import ProgramSourceState
from src.collectors.xinzhuang_awards_collector import XinzhuangAwardsCollector
from src.discovery.source_discovery_service import ProgramSourceDiscoveryService
from src.models.scholarship import Scholarship
from src.models.source_quality import SourceRisk


class ExpandedScholarshipCollector(LhuCollector):
    """既有官方來源、額外來源目錄及 TUN 指定方案監測群組。"""

    def __init__(
        self,
        source_url: str,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode = CollectionMode.INCREMENTAL,
        max_pages: int = 20,
        fetch_workers: int = 1,
        *,
        source_discovery: ProgramSourceDiscoveryService | None = None,
        source_discovery_min_score: int = 100,
        source_discovery_max_candidates: int = 5,
    ) -> None:
        super().__init__(
            source_url,
            timeout_seconds,
            user_agent,
            collection_mode,
            max_pages,
        )
        self.fetch_workers = fetch_workers
        self.source_discovery = source_discovery
        self.source_discovery_min_score = source_discovery_min_score
        self.source_discovery_max_candidates = source_discovery_max_candidates
        self.tun_collector: DecisionSafeTunProgramWatchCollector | None = None

    def collect(self) -> list[Scholarship]:
        self.tun_collector = DecisionSafeTunProgramWatchCollector(
            self.timeout_seconds,
            self.user_agent,
            self.collection_mode,
            self.max_pages,
            self.fetch_workers,
            source_discovery=self.source_discovery,
            source_discovery_min_score=self.source_discovery_min_score,
            source_discovery_max_candidates=self.source_discovery_max_candidates,
        )
        official_additions = [
            self._additional_collector(config)
            for config in OFFICIAL_ADDITIONAL_SOURCES
        ]
        broad_portals = [
            self._additional_collector(config)
            for config in BROAD_SCHOLARSHIP_PORTALS
        ]
        collectors: list[BaseCollector] = [
            _LhuOnlyCollector(self),
            HelpDreamsCollector(
                "moe-helpdreams-private",
                "教育部圓夢助學網－民間團體",
                _HELPDREAMS_PRIVATE_URL,
                self.timeout_seconds,
                self.user_agent,
            ),
            HelpDreamsCollector(
                "moe-helpdreams-government",
                "教育部圓夢助學網－政府機關",
                _HELPDREAMS_GOVERNMENT_URL,
                self.timeout_seconds,
                self.user_agent,
            ),
            IndigenousGrantCollector(
                _INDIGENOUS_GRANTS_URL,
                self.timeout_seconds,
                self.user_agent,
            ),
            MoeOverseasCollector(
                self.timeout_seconds,
                self.user_agent,
                self.collection_mode,
                self.max_pages,
            ),
            XinzhuangAwardsCollector(
                _XINZHUANG_AWARDS_URL,
                self.timeout_seconds,
                self.user_agent,
                self.collection_mode,
                self.max_pages,
            ),
            *official_additions,
            self.tun_collector,
            *broad_portals,
        ]
        self.multi_source = MultiSourceCollector(collectors)
        return self.multi_source.collect()

    def _additional_collector(
        self,
        config: AdditionalScholarshipSource,
    ) -> AdditionalScholarshipSourceCollector:
        return AdditionalScholarshipSourceCollector(
            config,
            self.timeout_seconds,
            self.user_agent,
            self.collection_mode,
            self.max_pages,
        )

    # 來源群組摘要後追加 URL 品質與 TUN 逐項狀態。
    def source_summary_lines(self) -> list[str]:
        lines = super().source_summary_lines()
        if self.tun_collector is not None:
            states = self.tun_collector.program_states
            lines.append(_tun_quality_summary(states))
            lines.extend(self.tun_collector.program_status_lines())
        return lines


# 彙整 URL 類型與高風險來源數，避免 HTTP 健康被誤認為品質合格。
def _tun_quality_summary(states: tuple[ProgramSourceState, ...]) -> str:
    types = Counter(item.source_url_type.value for item in states)
    type_text = "／".join(f"{name} {count}" for name, count in sorted(types.items()))
    high_risk = sum(
        item.update_risk in {SourceRisk.HIGH, SourceRisk.CRITICAL}
        for item in states
    )
    return f"TUN URL品質：{type_text}；高風險 {high_risk}"
