# -*- coding: utf-8 -*-

from src.collectors.base_collector import BaseCollector
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
from src.collectors.tun_program_watch_collector import TunProgramWatchCollector
from src.collectors.xinzhuang_awards_collector import XinzhuangAwardsCollector
from src.models.scholarship import Scholarship


class ExpandedScholarshipCollector(LhuCollector):
    """現有六個官方來源，加上 TUN 38 項方案的官方監測群組。"""

    def collect(self) -> list[Scholarship]:
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
            TunProgramWatchCollector(self.timeout_seconds, self.user_agent),
        ]
        self.multi_source = MultiSourceCollector(collectors)
        return self.multi_source.collect()
