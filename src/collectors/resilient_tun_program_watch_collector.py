# -*- coding: utf-8 -*-

from dataclasses import replace
from urllib.parse import urlparse

from src.catalogs.tun_live_contracts import LiveSourceCandidate, live_contract
from src.catalogs.tun_program_sources import ResolvedProgramSource, resolved_programs
from src.collectors.collection_diagnostics import CollectorDiagnostic
from src.collectors.listing_paginator import ListingCrawlResult, crawl_listing_pages
from src.collectors.tun_program_watch_collector import (
    PageDiscoveryDiagnostic,
    ProgramSourceState,
    TunProgramWatchCollector,
    _ProgramPageFetcher,
    _empty_group_diagnostic,
    _extract_program_notices_with_diagnostics,
    _merge_counts,
    _merge_discovery_diagnostics,
    _update_program_states,
)
from src.models.scholarship import Scholarship
from src.models.source_quality import SourceUrlType

_RETRYABLE_STATUSES = frozenset(
    {
        "fetch_failed",
        "matcher_miss",
        "match_ambiguous",
        "source_structure_changed",
    }
)
_SUCCESS_STATUSES = frozenset({"matched", "no_current_announcement"})
_STATUS_PRIORITY = {
    "matched": 6,
    "no_current_announcement": 5,
    "match_ambiguous": 4,
    "matcher_miss": 3,
    "source_structure_changed": 2,
    "fetch_failed": 1,
}


class ResilientTunProgramWatchCollector(TunProgramWatchCollector):
    """主入口失敗或 matcher miss 時，依 live 契約逐一嘗試安全回退來源。"""

    def collect(self) -> list[Scholarship]:
        records = super().collect()
        original_states = {item.program_id: item for item in self.program_states}
        source_by_id = {item.program_id: item for item in resolved_programs()}
        retry_stats = _RetryStats()

        for program_id, source in source_by_id.items():
            contract = live_contract(program_id)
            current = original_states[program_id]
            if current.status not in _RETRYABLE_STATUSES and not contract.force_replace:
                continue
            attempt = self._retry_program(source, retry_stats)
            if attempt is None:
                continue
            original_states[program_id] = attempt.state
            if attempt.state.status == "matched":
                records = _replace_program_records(
                    records,
                    program_id,
                    attempt.records,
                    contract.force_replace,
                )

        self.program_states = tuple(
            original_states[item.program_id] for item in resolved_programs()
        )
        self.diagnostic = _rebuild_diagnostic(
            self.diagnostic,
            self.program_states,
            retry_stats,
        )
        return records

    # 依 preferred、原入口與既有 fallback 順序嘗試，回傳最佳結果。
    def _retry_program(
        self,
        program: ResolvedProgramSource,
        stats: "_RetryStats",
    ) -> "_RetryAttempt | None":
        contract = live_contract(program.program_id)
        aliases = tuple(dict.fromkeys((*program.aliases, *contract.aliases)))
        variants = _source_variants(program, contract.preferred_sources)
        best: _RetryAttempt | None = None
        for candidate in variants:
            variant = replace(
                program,
                aliases=aliases,
                official_url=candidate.url,
                source_url_type=candidate.source_url_type,
            )
            attempt = self._collect_variant(variant, candidate.reason, stats)
            if best is None or _attempt_score(attempt) > _attempt_score(best):
                best = attempt
            if attempt.state.status in _SUCCESS_STATUSES:
                return attempt
        return best

    # 單一方案單一入口使用原 collector 的解析與診斷邏輯。
    def _collect_variant(
        self,
        program: ResolvedProgramSource,
        reason: str,
        stats: "_RetryStats",
    ) -> "_RetryAttempt":
        fetcher = _ProgramPageFetcher(
            self.timeout_seconds,
            self.user_agent,
            self.fetch_workers,
        )
        crawl = crawl_listing_pages(
            program.official_url,
            self.collection_mode,
            self.max_pages,
            fetcher.fetch_one,
            fetcher.fetch_many,
        )
        stats.add_crawl(crawl, fetcher.fallback_used)
        counts, discovery = _empty_group_diagnostic((program,))
        found: list[Scholarship] = []
        raw_matches = 0
        for page in crawl.pages:
            page_records, matched, page_counts, page_discovery = (
                _extract_program_notices_with_diagnostics(
                    page.html,
                    page.url,
                    program.official_url,
                    (program,),
                )
            )
            found.extend(page_records)
            raw_matches += matched
            _merge_counts(counts, page_counts)
            discovery = _merge_discovery_diagnostics(discovery, page_discovery)
        stats.raw_matches += raw_matches
        stats.parsed_records += len(found)
        states = {program.program_id: _placeholder_state(program)}
        _update_program_states(states, (program,), crawl, counts, discovery)
        state = states[program.program_id]
        state = replace(
            state,
            reason=f"production fallback：{reason} {state.reason}".strip(),
        )
        return _RetryAttempt(state, tuple(_unique_records(found)))


class _RetryStats:
    """彙整額外 live fallback 請求，回填群組診斷。"""

    def __init__(self) -> None:
        self.pages_detected = 0
        self.pages_requested = 0
        self.pages_succeeded = 0
        self.raw_matches = 0
        self.parsed_records = 0
        self.ssl_fallback = False

    def add_crawl(self, crawl: ListingCrawlResult, ssl_fallback: bool) -> None:
        self.pages_detected += crawl.pages_detected
        self.pages_requested += crawl.pages_requested
        self.pages_succeeded += crawl.pages_succeeded
        self.ssl_fallback = self.ssl_fallback or ssl_fallback


class _RetryAttempt:
    def __init__(
        self,
        state: ProgramSourceState,
        records: tuple[Scholarship, ...],
    ) -> None:
        self.state = state
        self.records = records


# 以 resolved source 建立可交給既有狀態更新函式的初始值。
def _placeholder_state(program: ResolvedProgramSource) -> ProgramSourceState:
    return ProgramSourceState(
        program.program_id,
        program.title,
        program.official_url,
        "configured",
        source_url_type=program.source_url_type,
        update_risk=program.update_risk,
    )


# preferred sources 優先，再接原入口與既有 fallback；URL 不重複。
def _source_variants(
    program: ResolvedProgramSource,
    preferred: tuple[LiveSourceCandidate, ...],
) -> tuple[LiveSourceCandidate, ...]:
    candidates = [
        *preferred,
        LiveSourceCandidate(
            program.official_url,
            program.source_url_type,
            "原始來源契約入口。",
        ),
        *(
            LiveSourceCandidate(
                url,
                _fallback_url_type(url, program.source_url_type),
                "來源契約 fallback。",
            )
            for url in program.fallback_urls
        ),
    ]
    unique: dict[str, LiveSourceCandidate] = {}
    for candidate in candidates:
        if candidate.url:
            unique.setdefault(candidate.url, candidate)
    return tuple(unique.values())


# 正式轉載單篇必須允許入口頁自身成為候選。
def _fallback_url_type(url: str, default: SourceUrlType) -> SourceUrlType:
    host = urlparse(url).hostname or ""
    detail_markers = ("/p/404-", "news_detail", "announcement.php?aid=", "/posts/")
    if any(marker in url for marker in detail_markers):
        if host.endswith(("edu.tw", "gov.tw")):
            return SourceUrlType.RELAY_DETAIL
        return SourceUrlType.ANNUAL_DETAIL
    return default


# matched 優先；其次正常無當期公告，再依技術錯誤層級排序。
def _attempt_score(attempt: _RetryAttempt) -> tuple[int, int, int]:
    state = attempt.state
    return (
        _STATUS_PRIORITY.get(state.status, 0),
        state.top_score,
        state.candidate_count,
    )


# 強制替換時移除舊錯頁候選；一般回退只補缺少的方案候選。
def _replace_program_records(
    records: list[Scholarship],
    program_id: str,
    replacements: tuple[Scholarship, ...],
    force_replace: bool,
) -> list[Scholarship]:
    kept = (
        [item for item in records if item.program_id != program_id]
        if force_replace
        else list(records)
    )
    seen = {item.content_hash for item in kept}
    for item in replacements:
        if item.content_hash not in seen:
            kept.append(item)
            seen.add(item.content_hash)
    return kept


# 同一 fallback 多個節點只保留唯一公告。
def _unique_records(records: list[Scholarship]) -> list[Scholarship]:
    unique: dict[str, Scholarship] = {}
    for item in records:
        unique.setdefault(item.content_hash, item)
    return list(unique.values())


# 以最後逐方案狀態重建群組成功數，不再保留已被 fallback 修復的 partial。
def _rebuild_diagnostic(
    base: CollectorDiagnostic,
    states: tuple[ProgramSourceState, ...],
    stats: _RetryStats,
) -> CollectorDiagnostic:
    failures = [item for item in states if item.status in _RETRYABLE_STATUSES]
    completeness = "partial" if failures else base.completeness
    if not failures and base.completeness == "partial":
        completeness = "complete"
    errors = "｜".join(
        f"{item.program_id}:{item.status}:{item.reason}" for item in failures[:10]
    )
    requested = base.pages_requested + stats.pages_requested
    succeeded = base.pages_succeeded + stats.pages_succeeded
    parsed = base.parsed_rows + stats.parsed_records
    raw = base.raw_rows + stats.raw_matches
    return replace(
        base,
        completeness=completeness,
        pages_detected=(base.pages_detected or 0) + stats.pages_detected,
        pages_requested=requested,
        pages_succeeded=succeeded,
        raw_rows=raw,
        parsed_rows=parsed,
        rejected_rows=max(raw - parsed, 0),
        stop_reason=(
            "program_watch_live_contract_passed"
            if not failures
            else "program_watch_live_contract_partial"
        ),
        error=errors,
        ssl_compatibility_fallback=(
            base.ssl_compatibility_fallback or stats.ssl_fallback
        ),
        child_sources_detected=len(states),
        child_sources_succeeded=len(states) - len(failures),
    )
