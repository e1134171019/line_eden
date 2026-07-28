# -*- coding: utf-8 -*-

from dataclasses import replace

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.models.scholarship import Scholarship


class EvidenceDetailFetcher(AnnouncementDetailFetcher):
    """保留完整診斷，正式資格文字只由 NoticeContent 建立。"""

    def fetch_with_diagnostics(self, scholarship: Scholarship) -> DetailFetchResult:
        result = super().fetch_with_diagnostics(scholarship)
        return replace(result, text=result.content.eligibility_text())

    def fetch_text(self, scholarship: Scholarship) -> str:
        return self.fetch_with_diagnostics(scholarship).content.eligibility_text()
