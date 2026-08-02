# -*- coding: utf-8 -*-

from urllib.parse import urlparse

from src.catalogs.tun_live_contracts import live_contract
from src.catalogs.tun_program_sources import ResolvedProgramSource, resolved_programs
from src.collectors.resilient_tun_program_watch_collector import (
    ResilientTunProgramWatchCollector,
)
from src.models.scholarship import Scholarship


class DecisionSafeTunProgramWatchCollector(ResilientTunProgramWatchCollector):
    """剔除 force-replace 頁面回連到舊導覽入口所產生的假申請候選。"""

    def collect(self) -> list[Scholarship]:
        records = super().collect()
        source_by_id = {item.program_id: item for item in resolved_programs()}
        return [
            item
            for item in records
            if not _is_replaced_navigation_candidate(
                item,
                source_by_id.get(item.program_id),
            )
        ]


# force-replace 已指定正式辦法頁時，不得再把原舊入口當成新的申請公告。
def _is_replaced_navigation_candidate(
    item: Scholarship,
    source: ResolvedProgramSource | None,
) -> bool:
    if source is None or not item.program_id:
        return False
    contract = live_contract(item.program_id)
    if not contract.force_replace or not contract.preferred_sources:
        return False
    original_url = source.official_url
    if not original_url:
        return False
    preferred_urls = {
        _canonical_url(candidate.url) for candidate in contract.preferred_sources
    }
    original = _canonical_url(original_url)
    if original in preferred_urls:
        return False
    record_urls = {
        _canonical_url(value)
        for value in (item.source_url, item.detail_url)
        if value
    }
    return original in record_urls


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
