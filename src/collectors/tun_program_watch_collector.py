# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import date
import re
import time
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
import httpx

from src.catalogs.tun_2025_program_catalog import (
    TUN_2025_PROGRAMS,
    ScholarshipProgramWatch,
)
from src.catalogs.tun_program_sources import (
    core_covered_programs,
    monitorable_programs,
    unresolved_programs,
)
from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectionMode, CollectorDiagnostic
from src.collectors.http_client import DetailSafeHttpClient
from src.collectors.listing_paginator import ListingCrawlResult, crawl_listing_pages
from src.models.scholarship import Scholarship

_GREGORIAN_DATE = re.compile(
    r"(?P<year>20\d{2})\s*(?:年|[-/.])\s*"
    r"(?P<month>\d{1,2})\s*(?:月|[-/.])\s*(?P<day>\d{1,2})\s*日?"
)
_ROC_DATE = re.compile(
    r"(?:民國\s*)?(?P<year>1\d{2})\s*年\s*"
    r"(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日?"
)
_CANDIDATE_SELECTORS = "a[href], article, li, tr, h1, h2, h3, h4"
_FETCH_ATTEMPTS = 2


class TunProgramWatchCollector(BaseCollector):
    """監測 38 項方案；完整稽核翻頁，每日模式只抓入口頁。"""

    source_label = "TUN 38方案官方監測"
    empty_is_healthy = True

    def __init__(
        self,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode = CollectionMode.INCREMENTAL,
        max_pages: int = 20,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.collection_mode = collection_mode
        self.max_pages = max_pages
        self.diagnostic = CollectorDiagnostic()

    def collect(self) -> list[Scholarship]:
        groups = _group_programs_by_url(monitorable_programs())
        core_covered = core_covered_programs()
        records: list[Scholarship] = []
        seen_records: set[str] = set()
        crawls: list[tuple[str, ListingCrawlResult]] = []
        successful_programs = len(core_covered)
        raw_matches = 0
        fallback_used = False

        with DetailSafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            for official_url, programs in groups.items():
                crawl = crawl_listing_pages(
                    official_url,
                    self.collection_mode,
                    self.max_pages,
                    lambda url: _fetch_text_with_retry(client, url),
                )
                crawls.append((official_url, crawl))
                if crawl.pages:
                    successful_programs += len(programs)
                for page in crawl.pages:
                    found, matched = _extract_program_notices(
                        page.html,
                        page.url,
                        programs,
                    )
                    raw_matches += matched
                    _append_unique(records, seen_records, found)
            fallback_used = bool(client.fallback_hosts)

        self.diagnostic = _build_diagnostic(
            crawls,
            len(records),
            raw_matches,
            successful_programs,
            fallback_used,
        )
        return records


# 彙整所有入口分頁結果，完整模式若任一網站缺頁即標示 partial。
def _build_diagnostic(
    crawls: list[tuple[str, ListingCrawlResult]],
    parsed_rows: int,
    raw_rows: int,
    successful_programs: int,
    fallback_used: bool,
) -> CollectorDiagnostic:
    unresolved_count = len(unresolved_programs())
    partial = [(url, item) for url, item in crawls if item.completeness == "partial"]
    failed = [(url, item) for url, item in crawls if not item.pages]
    mode = crawls[0][1].completeness if crawls else "unknown"
    completeness = "incremental" if mode == "incremental" else "complete"
    if unresolved_count or partial or failed:
        completeness = "partial"
    return CollectorDiagnostic(
        completeness=completeness,
        pages_detected=sum(item.pages_detected for _, item in crawls),
        pages_requested=sum(item.pages_requested for _, item in crawls),
        pages_succeeded=sum(item.pages_succeeded for _, item in crawls),
        raw_rows=raw_rows,
        parsed_rows=parsed_rows,
        rejected_rows=max(raw_rows - parsed_rows, 0),
        stop_reason=_watch_stop_reason(completeness),
        error=_diagnostic_error(unresolved_count, partial, failed),
        ssl_compatibility_fallback=fallback_used,
        child_sources_detected=len(TUN_2025_PROGRAMS),
        child_sources_succeeded=successful_programs,
    )


# 建立 partial 的實際網址與停止原因，避免只顯示模糊來源數量。
def _diagnostic_error(
    unresolved_count: int,
    partial: list[tuple[str, ListingCrawlResult]],
    failed: list[tuple[str, ListingCrawlResult]],
) -> str:
    parts: list[str] = []
    if unresolved_count:
        parts.append(f"可靠入口待確認 {unresolved_count}")
    if partial:
        detail = "｜".join(f"{url}（{item.stop_reason}）" for url, item in partial[:8])
        parts.append(f"分頁未完整 {len(partial)}：{detail}")
    if failed:
        detail = "｜".join(f"{url}（{';'.join(item.errors)}）" for url, item in failed[:8])
        parts.append(f"入口抓取失敗 {len(failed)}：{detail}")
    return "；".join(parts)


def _watch_stop_reason(completeness: str) -> str:
    if completeness == "incremental":
        return "program_watch_incremental_first_pages"
    if completeness == "complete":
        return "program_watch_all_detected_pages_completed"
    return "program_watch_partial"


# 依內容雜湊合併跨頁重複公告。
def _append_unique(
    records: list[Scholarship],
    seen_records: set[str],
    found: list[Scholarship],
) -> None:
    for item in found:
        if item.content_hash in seen_records:
            continue
        seen_records.add(item.content_hash)
        records.append(item)


def _fetch_text_with_retry(client: DetailSafeHttpClient, url: str) -> str:
    """只對 timeout／transport error 進行一次有限重試。"""

    last_error: Exception | None = None
    for attempt in range(_FETCH_ATTEMPTS):
        try:
            return client.get_text(url)
        except (httpx.TimeoutException, httpx.TransportError) as error:
            last_error = error
            if attempt + 1 < _FETCH_ATTEMPTS:
                time.sleep(0.5)
    assert last_error is not None
    raise last_error


def _group_programs_by_url(
    programs: tuple[ScholarshipProgramWatch, ...],
) -> dict[str, tuple[ScholarshipProgramWatch, ...]]:
    grouped: dict[str, list[ScholarshipProgramWatch]] = defaultdict(list)
    for program in programs:
        grouped[program.official_url].append(program)
    return {url: tuple(items) for url, items in grouped.items()}


def _extract_program_notices(
    html: str,
    official_url: str,
    programs: tuple[ScholarshipProgramWatch, ...],
) -> tuple[list[Scholarship], int]:
    soup = BeautifulSoup(html, "html.parser")
    for unwanted in soup.select("script, style, noscript, svg"):
        unwanted.decompose()

    records: list[Scholarship] = []
    matched_count = 0
    seen: set[str] = set()
    for node in soup.select(_CANDIDATE_SELECTORS):
        context = _candidate_context(node)
        if not context:
            continue
        for program in programs:
            if not _matches_program(context, program):
                continue
            matched_count += 1
            published_date = _extract_date(node, context)
            if published_date is None:
                continue
            source_url = _candidate_url(node, official_url)
            title = _candidate_title(node, program)
            key = f"{program.program_id}|{published_date}|{source_url}"
            if key in seen:
                continue
            seen.add(key)
            records.append(
                Scholarship.from_raw(
                    f"tun-program-{program.program_id}",
                    title,
                    published_date,
                    source_url,
                )
            )
    return records, matched_count


def _candidate_context(node: Tag) -> str:
    if node.name == "a":
        container = node.find_parent(("article", "li", "tr")) or node.parent or node
    else:
        container = node.find_parent("article") or node
    return " ".join(container.get_text(" ", strip=True).split())[:1200]


def _candidate_title(node: Tag, program: ScholarshipProgramWatch) -> str:
    if node.name == "a":
        text = " ".join(node.get_text(" ", strip=True).split())
        if len(text) >= 4:
            return text[:220]
    return program.title


def _candidate_url(node: Tag, official_url: str) -> str:
    link = node if node.name == "a" else node.find("a", href=True)
    if isinstance(link, Tag):
        href = str(link.get("href", "")).strip()
        if href and not href.lower().startswith(("javascript:", "mailto:", "tel:")):
            return urljoin(official_url, href)
    return official_url


def _matches_program(text: str, program: ScholarshipProgramWatch) -> bool:
    normalized = _normalize(text)
    return any(_normalize(alias) in normalized for alias in program.aliases)


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"[\W_]+", "", value)


def _extract_date(node: Tag, context: str) -> str | None:
    time_node = node.find("time") if node.name != "time" else node
    if isinstance(time_node, Tag):
        datetime_value = str(time_node.get("datetime", "")).strip()
        parsed = _parse_date(datetime_value)
        if parsed is not None:
            return parsed.isoformat()
    parsed = _parse_date(context)
    return parsed.isoformat() if parsed is not None else None


def _parse_date(text: str) -> date | None:
    for pattern, roc in ((_GREGORIAN_DATE, False), (_ROC_DATE, True)):
        match = pattern.search(text)
        if match is None:
            continue
        year = int(match.group("year")) + (1911 if roc else 0)
        month = int(match.group("month"))
        day = int(match.group("day"))
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None
