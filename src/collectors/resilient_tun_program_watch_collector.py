# -*- coding: utf-8 -*-

from collections import defaultdict
from dataclasses import dataclass, replace
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.catalogs.live_program_sources import (
    live_monitorable_programs,
    live_resolved_programs,
)
from src.catalogs.tun_program_sources import ResolvedProgramSource
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.listing_paginator import ListingCrawlResult, ListingPage, crawl_listing_pages
import src.collectors.tun_program_watch_collector as legacy
from src.models.scholarship import Scholarship

_SHARED_SUNSHINE_PROGRAM_IDS = {
    "sunshine-scholarship",
    "sunshine-wanzu",
}
_SHARED_SUNSHINE_ANNOUNCEMENT_TERMS = (
    "年度獎助學金相關簡章開放下載",
    "年度獎助學金申請公告",
)


class ResilientTunProgramWatchCollector(legacy.TunProgramWatchCollector):
    """主入口失敗或無候選時，依來源契約實際執行 fallback。"""

    def collect(self) -> list[Scholarship]:
        groups = _group_programs(live_monitorable_programs())
        records: list[Scholarship] = []
        seen_records: set[str] = set()
        crawls: list[tuple[str, ListingCrawlResult]] = []
        states = {
            item.program_id: legacy._initial_program_state(item)
            for item in live_resolved_programs()
        }
        successful_programs = 0
        raw_node_matches = 0
        source_fallback_used = False
        fetcher = legacy._ProgramPageFetcher(
            self.timeout_seconds,
            self.user_agent,
            self.fetch_workers,
        )

        for primary_url, programs in groups.items():
            result = _collect_program_group(
                primary_url,
                programs,
                self.collection_mode,
                self.max_pages,
                fetcher,
            )
            crawls.append((primary_url, result.crawl))
            if result.crawl.pages:
                successful_programs += len(programs)
            raw_node_matches += result.raw_node_matches
            source_fallback_used = source_fallback_used or result.fallback_used
            legacy._append_unique(records, seen_records, list(result.records))
            legacy._update_program_states(
                states,
                programs,
                result.crawl,
                result.counts,
                result.discovery,
            )
            _apply_actual_entry_urls(
                states,
                programs,
                primary_url,
                result.actual_entry_urls,
                result.first_success_url,
            )

        resolved = live_resolved_programs()
        self.program_states = tuple(states[item.program_id] for item in resolved)
        self.diagnostic = legacy._build_diagnostic(
            crawls,
            len(records),
            raw_node_matches,
            successful_programs,
            fetcher.fallback_used or source_fallback_used,
        )
        return records


@dataclass(frozen=True)
class _GroupResult:
    """單一主入口及其 fallback 的合併抓取結果。"""

    records: tuple[Scholarship, ...]
    crawl: ListingCrawlResult
    counts: dict[str, int]
    discovery: legacy.PageDiscoveryDiagnostic
    raw_node_matches: int
    actual_entry_urls: dict[str, str]
    first_success_url: str
    fallback_used: bool


# 同一主入口的 sibling programs 共用一次 fallback 鏈。
def _group_programs(
    programs: tuple[ResolvedProgramSource, ...],
) -> dict[str, tuple[ResolvedProgramSource, ...]]:
    grouped: dict[str, list[ResolvedProgramSource]] = defaultdict(list)
    for program in programs:
        grouped[program.official_url].append(program)
    return {url: tuple(items) for url, items in grouped.items()}


# 主入口無候選時依序檢查正式 fallback，直到所有 sibling 皆命中。
def _collect_program_group(
    primary_url: str,
    programs: tuple[ResolvedProgramSource, ...],
    collection_mode: CollectionMode,
    max_pages: int,
    fetcher: legacy._ProgramPageFetcher,
) -> _GroupResult:
    counts, discovery = legacy._empty_group_diagnostic(programs)
    records: list[Scholarship] = []
    seen_records: set[str] = set()
    crawls: list[tuple[str, ListingCrawlResult]] = []
    actual_entry_urls: dict[str, str] = {}
    raw_node_matches = 0
    first_success_url = ""

    for source_url in _candidate_urls(primary_url, programs):
        crawl = crawl_listing_pages(
            source_url,
            collection_mode,
            max_pages,
            fetcher.fetch_one,
            fetcher.fetch_many,
        )
        crawls.append((source_url, crawl))
        if not crawl.pages:
            continue
        if not first_success_url:
            first_success_url = source_url
        for page in crawl.pages:
            found, matched, page_counts, page_discovery = (
                legacy._extract_program_notices_with_diagnostics(
                    page.html,
                    page.url,
                    source_url,
                    programs,
                )
            )
            shared = _shared_announcement_records(
                page.html,
                page.url,
                source_url,
                programs,
            )
            _append_shared_records(found, page_counts, shared)
            matched += len(shared)
            raw_node_matches += matched
            legacy._merge_counts(counts, page_counts)
            discovery = legacy._merge_discovery_diagnostics(
                discovery,
                page_discovery,
            )
            for item in found:
                actual_entry_urls.setdefault(item.program_id, source_url)
            legacy._append_unique(records, seen_records, found)
        if all(counts.get(item.program_id, 0) > 0 for item in programs):
            break

    fallback_used = bool(
        (first_success_url and first_success_url != primary_url)
        or any(url != primary_url for url in actual_entry_urls.values())
    )
    aggregate = _aggregate_crawls(crawls, fallback_used)
    return _GroupResult(
        tuple(records),
        aggregate,
        dict(counts),
        discovery,
        raw_node_matches,
        actual_entry_urls,
        first_success_url,
        fallback_used,
    )


# 陽光年度簡章同時涵蓋兩個方案；不得用 sibling competition 只保留一個。
def _shared_announcement_records(
    html: str,
    page_url: str,
    entry_url: str,
    programs: tuple[ResolvedProgramSource, ...],
) -> list[Scholarship]:
    sunshine_programs = tuple(
        item for item in programs if item.program_id in _SHARED_SUNSHINE_PROGRAM_IDS
    )
    if len(sunshine_programs) != len(_SHARED_SUNSHINE_PROGRAM_IDS):
        return []

    soup = BeautifulSoup(html, "html.parser")
    records: list[Scholarship] = []
    seen_details: set[str] = set()
    for anchor in soup.select("a[href]"):
        title = " ".join(anchor.get_text(" ", strip=True).split())
        matched_term = next(
            (
                term
                for term in _SHARED_SUNSHINE_ANNOUNCEMENT_TERMS
                if term in title
            ),
            "",
        )
        if not matched_term:
            continue
        detail_url = urljoin(page_url, str(anchor.get("href", "")))
        if not detail_url or detail_url in seen_details:
            continue
        seen_details.add(detail_url)
        context = anchor.parent.get_text(" ", strip=True) if anchor.parent else title
        published_date = legacy._extract_date(anchor, context) or ""
        for program in sunshine_programs:
            records.append(
                Scholarship.from_raw(
                    source=f"tun-program-{program.program_id}",
                    title=title,
                    published_date=published_date,
                    source_url=detail_url,
                    program_id=program.program_id,
                    entry_url=entry_url,
                    detail_url=detail_url,
                    match_method="shared_announcement",
                    match_score=100,
                    matched_alias=matched_term,
                )
            )
    return records


# 合併共同公告時，避免與一般 matcher 已找到的同方案同明細重複。
def _append_shared_records(
    found: list[Scholarship],
    page_counts: dict[str, int],
    shared: list[Scholarship],
) -> None:
    existing = {(item.program_id, item.detail_url) for item in found}
    for item in shared:
        key = (item.program_id, item.detail_url)
        if key in existing:
            continue
        existing.add(key)
        found.append(item)
        page_counts[item.program_id] = page_counts.get(item.program_id, 0) + 1


# 主入口優先，其後合併 sibling programs 的 fallback 並去重。
def _candidate_urls(
    primary_url: str,
    programs: tuple[ResolvedProgramSource, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            url
            for url in (
                primary_url,
                *(url for item in programs for url in item.fallback_urls),
            )
            if url
        )
    )


# 有任何成功入口時，以成功頁面為準；全部失敗才回報 fetch_failed。
def _aggregate_crawls(
    attempts: list[tuple[str, ListingCrawlResult]],
    fallback_used: bool,
) -> ListingCrawlResult:
    successful = [(url, item) for url, item in attempts if item.pages]
    if not successful:
        errors = tuple(error for _, item in attempts for error in item.errors)
        return ListingCrawlResult(
            tuple(),
            len(attempts) or 1,
            sum(item.pages_requested for _, item in attempts) or 1,
            0,
            "partial",
            "all_source_candidates_failed",
            errors,
        )

    pages = _unique_pages(successful)
    partial = any(item.completeness == "partial" for _, item in successful)
    stop_reason = "source_fallback_used" if fallback_used else "source_candidate_completed"
    return ListingCrawlResult(
        pages,
        sum(item.pages_detected for _, item in successful),
        sum(item.pages_requested for _, item in successful),
        len(pages),
        "partial" if partial else "complete",
        stop_reason,
        tuple(),
    )


# 同一頁可能同時由主入口和 fallback 發現，只保留一次。
def _unique_pages(
    crawls: list[tuple[str, ListingCrawlResult]],
) -> tuple[ListingPage, ...]:
    pages: list[ListingPage] = []
    seen: set[str] = set()
    for _, crawl in crawls:
        for page in crawl.pages:
            if page.url in seen:
                continue
            seen.add(page.url)
            pages.append(page)
    return tuple(pages)


# 狀態列顯示真正產生候選或至少成功讀取的入口。
def _apply_actual_entry_urls(
    states: dict[str, legacy.ProgramSourceState],
    programs: tuple[ResolvedProgramSource, ...],
    primary_url: str,
    actual_entry_urls: dict[str, str],
    first_success_url: str,
) -> None:
    for program in programs:
        state = states[program.program_id]
        actual = actual_entry_urls.get(program.program_id) or first_success_url or primary_url
        reason = state.reason
        if actual != primary_url:
            reason = f"主入口未完成，已改用 fallback：{actual}。{reason}"
        states[program.program_id] = replace(
            state,
            entry_url=actual,
            reason=reason,
        )
