# -*- coding: utf-8 -*-

from dataclasses import replace

import pytest

from src.catalogs.tun_live_contracts import LiveSourceCandidate
from src.catalogs.tun_program_sources import resolved_programs
from src.collectors.collection_diagnostics import CollectionMode
import src.collectors.resilient_tun_program_watch_collector as resilient_module
from src.collectors.resilient_tun_program_watch_collector import (
    ResilientTunProgramWatchCollector,
    _RetryAttempt,
    _RetryStats,
)
from src.collectors.tun_program_watch_collector import ProgramSourceState
from src.discovery.search_provider import SearchHit
from src.discovery.source_discovery_service import ProgramSourceDiscoveryService
from src.models.scholarship import Scholarship
from src.models.source_quality import SourceUrlType


class _SearchProvider:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        _ = query, limit
        self.calls += 1
        return [
            SearchHit(
                "賑災基金會助學金115年第1學期申請辦法",
                "https://www.tf4dr.org/posts/999",
                "財團法人賑災基金會申請資格",
                "2026-08-01",
            )
        ]


def _tf4dr_source():
    return next(item for item in resolved_programs() if item.program_id == "tf4dr-aid")


def _state(status: str, url: str, *, score: int = 0) -> ProgramSourceState:
    source = _tf4dr_source()
    return ProgramSourceState(
        source.program_id,
        source.title,
        url,
        status,
        source_url_type=SourceUrlType.ANNUAL_DETAIL,
        update_risk=source.update_risk,
        top_score=score,
    )


# 完整稽核在既有入口未命中時，應搜尋、驗證並採用新年度頁面。
def test_full_audit_uses_verified_runtime_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _tf4dr_source()
    provider = _SearchProvider()
    collector = ResilientTunProgramWatchCollector(
        1,
        "ua",
        CollectionMode.FULL_AUDIT,
        1,
        1,
        source_discovery=ProgramSourceDiscoveryService(provider, 5),
        source_discovery_min_score=100,
        source_discovery_max_candidates=2,
    )
    known = LiveSourceCandidate(
        "https://www.tf4dr.org/posts",
        SourceUrlType.LIST,
        "known",
    )
    record = Scholarship.from_raw(
        "tun-program-tf4dr-aid",
        "賑災基金會助學金115年第1學期",
        "2026-08-01",
        "https://www.tf4dr.org/posts/999",
        program_id="tf4dr-aid",
    )
    monkeypatch.setattr(resilient_module, "_source_variants", lambda *_args, **_kw: (known,))
    monkeypatch.setattr(collector, "_verify_discovered_page", lambda *_: True)

    def collect_variant(program, reason: str, _stats: _RetryStats) -> _RetryAttempt:
        if reason.startswith("runtime source discovery"):
            return _RetryAttempt(_state("matched", program.official_url, score=120), (record,))
        return _RetryAttempt(_state("matcher_miss", program.official_url, score=60), tuple())

    monkeypatch.setattr(collector, "_collect_variant", collect_variant)

    result = collector._retry_program(source, _RetryStats())

    assert result is not None
    assert result.state.status == "matched"
    assert result.records == (record,)
    assert provider.calls >= 1


# 日常增量模式即使有搜尋服務，也不得消耗搜尋額度。
def test_incremental_mode_does_not_run_paid_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _tf4dr_source()
    provider = _SearchProvider()
    collector = ResilientTunProgramWatchCollector(
        1,
        "ua",
        CollectionMode.INCREMENTAL,
        source_discovery=ProgramSourceDiscoveryService(provider, 5),
    )
    known = LiveSourceCandidate(
        "https://www.tf4dr.org/posts",
        SourceUrlType.LIST,
        "known",
    )
    monkeypatch.setattr(resilient_module, "_source_variants", lambda *_args, **_kw: (known,))
    monkeypatch.setattr(
        collector,
        "_collect_variant",
        lambda program, _reason, _stats: _RetryAttempt(
            _state("no_current_announcement", program.official_url),
            tuple(),
        ),
    )

    result = collector._retry_program(source, _RetryStats())

    assert result is not None
    assert result.state.status == "no_current_announcement"
    assert provider.calls == 0


# 搜尋結果即使分數夠高，未通過原頁身分驗證也不得進入 collector。
def test_unverified_discovery_candidate_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = replace(_tf4dr_source(), official_url="https://invalid.example/list")
    provider = _SearchProvider()
    collector = ResilientTunProgramWatchCollector(
        1,
        "ua",
        CollectionMode.FULL_AUDIT,
        source_discovery=ProgramSourceDiscoveryService(provider, 5),
    )
    monkeypatch.setattr(collector, "_verify_discovered_page", lambda *_: False)

    candidates = collector._discovered_source_variants(source, source.aliases, set())

    assert candidates == tuple()
    assert provider.calls >= 1
