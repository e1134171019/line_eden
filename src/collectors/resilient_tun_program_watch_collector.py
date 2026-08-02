# -*- coding: utf-8 -*-

from collections import defaultdict
from dataclasses import replace

from src.catalogs.live_tun_sources import (
    live_monitorable_programs,
    live_resolved_programs,
)
from src.catalogs.tun_program_sources import (
    ResolvedProgramSource,
    core_covered_programs,
)
from src.collectors.listing_paginator import ListingCrawlResult, crawl_listing_pages
from src.collectors.tun_program_watch_collector import (
    PageDiscoveryDiagnostic,
    ProgramMatchObservation,
    ProgramSourceState,
    TunProgramWatchCollector,
    _ProgramPageFetcher,
    _append_unique,
    _build_diagnostic,
    _empty_group_diagnostic,
    _extract_program_notices_with_diagnostics,
    _group_programs_by_url,
    _initial_program_state,
    _merge_counts,
    _merge_discovery_diagnostics,
    _update_program_states,
)
from src.models.scholarship import Scholarship
from src.models.source_quality import allows_direct_candidate

_DIRECT_MATCH_METHOD = "source_contract_direct"
_DIRECT_MATCH_SCORE = 100


class ResilientTunProgramWatchCollector(TunProgramWatchCollector):
    """主入口失敗時實際依來源契約輪詢 fallback，而非只保存 metadata。"""

    def collect(self) -> list[Scholarship]:
        programs = live_monitorable_programs()
        groups = _group_programs_by_url(programs)
        records: list[Scholarship] = []
        seen_records: set[str] = set()
        crawls: list[tuple[str, ListingCrawlResult]] = []
        states = {
            item.program_id: _initial_program_state(item)
            for item in live_resolved_programs()
        }
        successful_programs = len(core_covered_programs())
        raw_node_matches = 0
        fetcher = _ProgramPageFetcher(
            self.timeout_seconds,
            self.user_agent,
            self.fetch_workers,
        )

        for primary_url, group in groups.items():
            primary_crawl = self._crawl(primary_url, fetcher)
            if primary_crawl.pages:
                crawls.append((primary_url, primary_crawl))
                successful_programs += len(group)
                raw_node_matches += _process_group(
                    group,
                    primary_url,
                    primary_crawl,
                    states,
                    records,
                    seen_records,
                )
                continue

            for program in group:
                effective, crawl, used_fallback = self._crawl_program_fallbacks(
                    program,
                    primary_crawl,
                    fetcher,
                )
                crawls.append((effective.official_url, crawl))
                if crawl.pages:
                    successful_programs += 1
                raw_node_matches += _process_group(
                    (effective,),
                    effective.official_url,
                    crawl,
                    states,
                    records,
                    seen_records,
                )
                if used_fallback:
                    states[program.program_id] = _mark_fallback(
                        states[program.program_id],
                        primary_url,
                        effective.official_url,
                    )

        self.program_states = tuple(
            states[item.program_id] for item in live_resolved_programs()
        )
        self.diagnostic = _build_diagnostic(
            crawls,
            len(records),
            raw_node_matches,
            successful_programs,
            fetcher.fallback_used,
        )
        return records

    def _crawl(
        self,
        url: str,
        fetcher: _ProgramPageFetcher,
    ) -> ListingCrawlResult:
        return crawl_listing_pages(
            url,
            self.collection_mode,
            self.max_pages,
            fetcher.fetch_one,
            fetcher.fetch_many,
        )

    def _crawl_program_fallbacks(
        self,
        program: ResolvedProgramSource,
        primary_crawl: ListingCrawlResult,
        fetcher: _ProgramPageFetcher,
    ) -> tuple[ResolvedProgramSource, ListingCrawlResult, bool]:
        errors = list(primary_crawl.errors)
        for fallback_url in program.fallback_urls:
            fallback_crawl = self._crawl(fallback_url, fetcher)
            if fallback_crawl.pages:
                return replace(program, official_url=fallback_url), fallback_crawl, True
            errors.extend(fallback_crawl.errors)
        return program, replace(primary_crawl, errors=tuple(errors)), False


# 對一個實際成功或最終失敗的入口執行候選抽取與狀態更新。
def _process_group(
    programs: tuple[ResolvedProgramSource, ...],
    entry_url: str,
    crawl: ListingCrawlResult,
    states: dict[str, ProgramSourceState],
    records: list[Scholarship],
    seen_records: set[str],
) -> int:
    counts: dict[str, int] = defaultdict(int)
    _, diagnostic = _empty_group_diagnostic(programs)
    raw_node_matches = 0
    for page in crawl.pages:
        found, matched, page_counts, page_diagnostic = (
            _extract_program_notices_with_diagnostics(
                page.html,
                page.url,
                entry_url,
                programs,
            )
        )
        raw_node_matches += matched
        _merge_counts(counts, page_counts)
        diagnostic = _merge_discovery_diagnostics(diagnostic, page_diagnostic)
        _append_unique(records, seen_records, found)
    direct_matches, diagnostic = _append_direct_candidate_if_allowed(
        programs,
        entry_url,
        crawl,
        counts,
        diagnostic,
        records,
        seen_records,
    )
    raw_node_matches += direct_matches
    _update_program_states(states, programs, crawl, counts, diagnostic)
    return raw_node_matches


# 固定方案頁與單篇公告成功下載時，不強迫頁內再出現同名導覽連結。
def _append_direct_candidate_if_allowed(
    programs: tuple[ResolvedProgramSource, ...],
    entry_url: str,
    crawl: ListingCrawlResult,
    counts: dict[str, int],
    diagnostic: PageDiscoveryDiagnostic,
    records: list[Scholarship],
    seen_records: set[str],
) -> tuple[int, PageDiscoveryDiagnostic]:
    if len(programs) != 1 or not crawl.pages:
        return 0, diagnostic
    program = programs[0]
    if counts.get(program.program_id) or not allows_direct_candidate(
        program.source_url_type
    ):
        return 0, diagnostic
    page_url = crawl.pages[0].url
    candidate = Scholarship.from_raw(
        f"tun-program-{program.program_id}",
        program.title,
        "",
        page_url,
        program_id=program.program_id,
        entry_url=entry_url,
        detail_url=page_url,
        match_method=_DIRECT_MATCH_METHOD,
        match_score=_DIRECT_MATCH_SCORE,
        matched_alias=program.title,
    )
    before = len(records)
    _append_unique(records, seen_records, [candidate])
    if len(records) == before:
        return 0, diagnostic
    counts[program.program_id] = 1
    observations = dict(diagnostic.observations)
    current = observations.get(program.program_id, ProgramMatchObservation())
    observations[program.program_id] = ProgramMatchObservation(
        current.raw_candidates + 1,
        current.ambiguous_candidates,
        max(current.top_score, _DIRECT_MATCH_SCORE),
        current.second_best_score,
        _DIRECT_MATCH_METHOD,
        current.competing_program_id,
    )
    return 1, PageDiscoveryDiagnostic(
        observations,
        diagnostic.generic_candidates,
        diagnostic.link_candidates,
    )


# fallback 成功必須在逐方案狀態中留下可稽核軌跡。
def _mark_fallback(
    state: ProgramSourceState,
    primary_url: str,
    fallback_url: str,
) -> ProgramSourceState:
    reason = (
        f"主入口 {primary_url} 失敗，已使用 fallback {fallback_url}。"
        f"{state.reason}"
    )
    return replace(state, entry_url=fallback_url, reason=reason)
