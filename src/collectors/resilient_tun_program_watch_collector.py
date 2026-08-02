# -*- coding: utf-8 -*-

from collections import defaultdict
from dataclasses import replace

from src.catalogs.live_tun_sources import (
    live_monitorable_programs,
    live_resolved_programs,
)
from src.catalogs.tun_program_sources import core_covered_programs
from src.collectors.listing_paginator import ListingCrawlResult, crawl_listing_pages
from src.collectors.tun_program_watch_collector import (
    PageDiscoveryDiagnostic,
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
        program: object,
        primary_crawl: ListingCrawlResult,
        fetcher: _ProgramPageFetcher,
    ) -> tuple[object, ListingCrawlResult, bool]:
        errors = list(primary_crawl.errors)
        for fallback_url in getattr(program, "fallback_urls", tuple()):
            fallback_crawl = self._crawl(fallback_url, fetcher)
            if fallback_crawl.pages:
                return replace(program, official_url=fallback_url), fallback_crawl, True
            errors.extend(fallback_crawl.errors)
        return program, replace(primary_crawl, errors=tuple(errors)), False


# 對一個實際成功或最終失敗的入口執行候選抽取與狀態更新。
def _process_group(
    programs: tuple[object, ...],
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
    _update_program_states(states, programs, crawl, counts, diagnostic)
    return raw_node_matches


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
