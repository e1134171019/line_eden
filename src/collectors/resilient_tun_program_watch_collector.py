# -*- coding: utf-8 -*-

from dataclasses import replace

from src.catalogs.runtime_program_sources import (
    runtime_monitorable_programs,
    runtime_resolved_programs,
)
from src.catalogs.tun_program_sources import ResolvedProgramSource
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.listing_paginator import ListingCrawlResult, crawl_listing_pages
from src.collectors.tun_program_watch_collector import (
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
    """正式來源失效時使用已核對 fallback，並保留實際入口診斷。"""

    def collect(self) -> list[Scholarship]:
        programs_all = runtime_resolved_programs()
        groups = _group_programs_by_url(runtime_monitorable_programs())
        records: list[Scholarship] = []
        seen_records: set[str] = set()
        crawls: list[tuple[str, ListingCrawlResult]] = []
        states = {
            item.program_id: _initial_program_state(item)
            for item in programs_all
        }
        successful_programs = 0
        raw_node_matches = 0
        fetcher = _ProgramPageFetcher(
            self.timeout_seconds,
            self.user_agent,
            self.fetch_workers,
        )

        for primary_url, programs in groups.items():
            entry_url, crawl, attempts = _crawl_with_fallback(
                programs,
                self.collection_mode,
                self.max_pages,
                fetcher,
            )
            crawls.append((entry_url, crawl))
            if crawl.pages:
                successful_programs += len(programs)
            counts, diagnostic = _empty_group_diagnostic(programs)
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
                diagnostic = _merge_discovery_diagnostics(
                    diagnostic,
                    page_diagnostic,
                )
                _append_unique(records, seen_records, found)
            _update_program_states(states, programs, crawl, counts, diagnostic)
            _record_effective_entry(
                states,
                programs,
                primary_url,
                entry_url,
                attempts,
            )

        self.program_states = tuple(
            states[item.program_id] for item in programs_all
        )
        self.diagnostic = _build_diagnostic(
            crawls,
            len(records),
            raw_node_matches,
            successful_programs,
            fetcher.fallback_used,
        )
        return records


# 主入口完全失敗時，才依資料契約順序嘗試 fallback。
def _crawl_with_fallback(
    programs: tuple[ResolvedProgramSource, ...],
    collection_mode: CollectionMode,
    max_pages: int,
    fetcher: _ProgramPageFetcher,
) -> tuple[str, ListingCrawlResult, tuple[tuple[str, ListingCrawlResult], ...]]:
    attempts: list[tuple[str, ListingCrawlResult]] = []
    for url in _source_candidates(programs):
        crawl = crawl_listing_pages(
            url,
            collection_mode,
            max_pages,
            fetcher.fetch_one,
            fetcher.fetch_many,
        )
        attempts.append((url, crawl))
        if crawl.pages:
            return url, crawl, tuple(attempts)
    return programs[0].official_url, _all_failed_result(attempts), tuple(attempts)


# 同一主入口群組合併各方案 fallback，保持人工設定順序並去重。
def _source_candidates(
    programs: tuple[ResolvedProgramSource, ...],
) -> tuple[str, ...]:
    values: list[str] = [programs[0].official_url]
    for program in programs:
        values.extend(program.fallback_urls)
    return tuple(dict.fromkeys(value for value in values if value))


# 所有入口失敗時合併錯誤，避免只看到最後一個 URL。
def _all_failed_result(
    attempts: list[tuple[str, ListingCrawlResult]],
) -> ListingCrawlResult:
    errors: list[str] = []
    for url, crawl in attempts:
        if crawl.errors:
            errors.extend(crawl.errors)
        else:
            errors.append(f"{url}（入口未回傳可解析頁面）")
    return ListingCrawlResult(
        tuple(),
        len(attempts),
        sum(item.pages_requested for _, item in attempts),
        0,
        "partial",
        "all_source_candidates_failed",
        tuple(dict.fromkeys(errors)),
    )


# 狀態列顯示實際入口；fallback 成功時保留主入口失敗軌跡。
def _record_effective_entry(
    states: dict[str, ProgramSourceState],
    programs: tuple[ResolvedProgramSource, ...],
    primary_url: str,
    entry_url: str,
    attempts: tuple[tuple[str, ListingCrawlResult], ...],
) -> None:
    fallback_used = entry_url != primary_url and bool(attempts[-1][1].pages)
    attempt_reason = _failed_attempt_reason(attempts[:-1]) if fallback_used else ""
    for program in programs:
        state = states[program.program_id]
        reason = state.reason
        if fallback_used:
            prefix = f"主入口失敗後改用 fallback：{entry_url}。"
            if attempt_reason:
                prefix += f" 前序錯誤：{attempt_reason}。"
            reason = f"{prefix} {reason}".strip()
        states[program.program_id] = replace(
            state,
            entry_url=entry_url,
            reason=reason,
        )


# 壓縮前序失敗入口，供 LINE 與 source-health 追蹤。
def _failed_attempt_reason(
    attempts: tuple[tuple[str, ListingCrawlResult], ...],
) -> str:
    parts: list[str] = []
    for url, crawl in attempts:
        detail = "；".join(crawl.errors) or crawl.stop_reason
        parts.append(f"{url}（{detail}）")
    return "｜".join(parts)[:1000]
