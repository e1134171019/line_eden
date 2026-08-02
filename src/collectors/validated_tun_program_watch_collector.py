# -*- coding: utf-8 -*-

from collections import Counter
from dataclasses import replace
from urllib.parse import urlparse

from src.catalogs.tun_live_contracts import live_contract
from src.collectors.resilient_tun_program_watch_collector import (
    ResilientTunProgramWatchCollector,
    _RetryStats,
    _rebuild_diagnostic,
)
from src.models.scholarship import Scholarship


class ValidatedTunProgramWatchCollector(ResilientTunProgramWatchCollector):
    """移除 detail／evergreen 頁面中返回上層導覽的假公告候選。"""

    def collect(self) -> list[Scholarship]:
        records = super().collect()
        filtered = [item for item in records if not _is_upward_navigation_candidate(item)]
        counts = Counter(
            item.program_id for item in filtered if item.program_id
        )
        states = []
        for state in self.program_states:
            contract = live_contract(state.program_id)
            if not contract.force_replace:
                states.append(state)
                continue
            candidate_count = counts.get(state.program_id, 0)
            if state.status == "matched" and candidate_count == 0:
                states.append(
                    replace(
                        state,
                        status="matcher_miss",
                        candidate_count=0,
                        reason=(
                            "來源只產生返回上層導覽的假候選，"
                            "沒有可進入正文判斷的方案頁。"
                        ),
                    )
                )
                continue
            states.append(replace(state, candidate_count=candidate_count))
        self.program_states = tuple(states)
        self.diagnostic = _rebuild_diagnostic(
            self.diagnostic,
            self.program_states,
            _RetryStats(),
        )
        return filtered


# 同 host 下，候選 URL 是 entry URL 的上層路徑時視為導覽，不是公告。
def _is_upward_navigation_candidate(item: Scholarship) -> bool:
    if not item.program_id or not live_contract(item.program_id).force_replace:
        return False
    entry = urlparse(item.entry_url)
    detail = urlparse(item.detail_url)
    if not entry.hostname or entry.hostname != detail.hostname:
        return False
    entry_path = _normalized_path(entry.path)
    detail_path = _normalized_path(detail.path)
    if entry_path == detail_path:
        return False
    return entry_path.startswith(f"{detail_path}/")


# 路徑統一去除尾端斜線；根目錄保留單一斜線。
def _normalized_path(path: str) -> str:
    normalized = "/" + path.strip("/")
    return normalized.rstrip("/") or "/"
