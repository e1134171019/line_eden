# -*- coding: utf-8 -*-

from dataclasses import replace

from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.models.scholarship import Scholarship


class EvidenceDetailFetcher(AnnouncementDetailFetcher):
    """優先使用正文 URL，保留完整診斷且不傳遞 legacy marker。"""

    def fetch_with_diagnostics(self, scholarship: Scholarship) -> DetailFetchResult:
        detail_url = scholarship.detail_url or scholarship.source_url
        resolved = (
            scholarship
            if scholarship.source_url == detail_url
            else replace(scholarship, source_url=detail_url)
        )
        result = super().fetch_with_diagnostics(resolved)
        return replace(result, text=result.eligibility_text())

    def fetch_text(self, scholarship: Scholarship) -> str:
        return self.fetch_with_diagnostics(scholarship).text
