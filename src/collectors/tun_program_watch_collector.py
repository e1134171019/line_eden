# -*- coding: utf-8 -*-

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
import re
import time
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
    resolved_programs,
    unresolved_programs,
)
from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectionMode, CollectorDiagnostic
from src.collectors.http_client import DetailSafeHttpClient
from src.collectors.listing_paginator import ListingCrawlResult, crawl_listing_pages
from src.matchers.program_name_matcher import ProgramMatchResult, match_program
from src.models.scholarship import Scholarship
from src.models.source_quality import (
    SourceRisk,
    SourceUrlType,
    allows_direct_candidate,
)

_GREGORIAN_DATE = re.compile(
    r"(?P<year>20\d{2})\s*(?:年|[-/.])\s*"
    r"(?P<month>\d{1,2})\s*(?:月|[-/.])\s*(?P<day>\d{1,2})\s*日?"
)
_ROC_DATE = re.compile(
    r"(?:民國\s*)?(?P<year>1\d{2})\s*年\s*"
    r"(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日?"
)
_CANDIDATE_SELECTORS = "a[href], article, li, tr, h1, h2, h3, h4"
_FETCH_ATTEMPTS = 3
_MIN_TITLE_CONTEXT_LENGTH = 6


@dataclass(frozen=True)
class ProgramSourceState:
    """單一 TUN 方案在本次執行中的來源品質與唯一候選狀態。"""

    program_id: str
    title: str
    entry_url: str
    status: str
    candidate_count: int = 0
    reason: str = ""
    source_url_type: SourceUrlType = SourceUrlType.PENDING
    update_risk: SourceRisk = SourceRisk.HIGH


class TunProgramWatchCollector(BaseCollector):
    """監測 38 項方案；完整稽核有限併發翻頁，每日只抓入口頁。"""

    source_label = "TUN 38方案官方監測"
    empty_is_healthy = True

    def __init__(
        self,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode = CollectionMode.INCREMENTAL,
        max_pages: int = 20,
        fetch_workers: int = 1,
    ) -> None:
        if fetch_workers < 1:
            raise ValueError("fetch_workers 必須大於 0。")
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.collection_mode = collection_mode
        self.max_pages = max_pages
        self.fetch_workers = fetch_workers
        self.diagnostic = CollectorDiagnostic()
        self.program_states = _initial_program_states()

    def collect(self) -> list[Scholarship]:
        groups = _group_programs_by_url(monitorable_programs())
        core_covered = core_covered_programs()
        records: list[Scholarship] = []
        seen_records: set[str] = set()
        crawls: list[tuple[str, ListingCrawlResult]] = []
        successful_programs = len(core_covered)
        raw_node_matches = 0
        states = {item.program_id: item for item in _initial_program_states()}
        fetcher = _ProgramPageFetcher(
            self.timeout_seconds,
            self.user_agent,
            self.fetch_workers,
        )

        for official_url, programs in groups.items():
            crawl = crawl_listing_pages(
                official_url,
                self.collection_mode,
                self.max_pages,
                fetcher.fetch_one,
                fetcher.fetch_many,
            )
            crawls.append((official_url, crawl))
            if crawl.pages:
                successful_programs += len(programs)
            unique_counts: dict[str, int] = defaultdict(int)
            for page in crawl.pages:
                found, raw_matched, page_counts = _extract_program_notices_with_counts(
                    page.html,
                    page.url,
                    official_url,
                    programs,
                )
                raw_node_matches += raw_matched
                for program_id, count in page_counts.items():
                    unique_counts[program_id] += count
                _append_unique(records, seen_records, found)
            _update_program_states(states, programs, crawl, unique_counts)

        self.program_states = tuple(states[item.program_id] for item in resolved_programs())
        self.diagnostic = _build_diagnostic(
            crawls,
            len(records),
            raw_node_matches,
            successful_programs,
            fetcher.fallback_used,
        )
        return records

    def program_status_lines(self) -> list[str]:
        return [
            (
                f"TUN方案 {item.program_id}：{item.status}；"
                f"唯一候選 {item.candidate_count}；"
                f"入口 {item.entry_url or '由核心來源涵蓋'}；"
                f"URL類型 {item.source_url_type.value}；"
                f"風險 {item.update_risk.value}"
                + (f"；{item.reason}" if item.reason else "")
            )
            for item in self.program_states
        ]


class _ProgramPageFetcher:
    """每個工作執行緒重用一個 HTTP client，降低 TLS 與連線壓力。"""

    def __init__(self, timeout_seconds: float, user_agent: str, workers: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.workers = workers
        self.fallback_used = False

    def fetch_one(self, url: str) -> str:
        with DetailSafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            html = _fetch_text_with_retry(client, url)
            self.fallback_used = self.fallback_used or bool(client.fallback_hosts)
            return html

    def fetch_many(
        self,
        urls: tuple[str, ...],
    ) -> tuple[dict[str, str], dict[str, str]]:
        pages: dict[str, str] = {}
        errors: dict[str, str] = {}
        chunks = _chunk_urls(urls, self.workers)
        with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
            futures = [executor.submit(self._fetch_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                chunk_pages, chunk_errors, fallback_used = future.result()
                pages.update(chunk_pages)
                errors.update(chunk_errors)
                self.fallback_used = self.fallback_used or fallback_used
        return (
            {url: pages[url] for url in urls if url in pages},
            {url: errors[url] for url in urls if url in errors},
        )

    def _fetch_chunk(
        self,
        urls: tuple[str, ...],
    ) -> tuple[dict[str, str], dict[str, str], bool]:
        pages: dict[str, str] = {}
        errors: dict[str, str] = {}
        with DetailSafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            for url in urls:
                try:
                    pages[url] = _fetch_text_with_retry(client, url)
                except Exception as error:
                    errors[url] = _error_text(error)
            fallback_used = bool(client.fallback_hosts)
        return pages, errors, fallback_used


# 將分頁網址輪詢分配到固定工作數。
def _chunk_urls(urls: tuple[str, ...], workers: int) -> tuple[tuple[str, ...], ...]:
    worker_count = min(workers, len(urls))
    return tuple(tuple(urls[index::worker_count]) for index in range(worker_count))


# 依 URL 品質建立尚未執行的 38 項初始狀態。
def _initial_program_states() -> tuple[ProgramSourceState, ...]:
    core_ids = {item.program_id for item in core_covered_programs()}
    pending_ids = {item.program_id for item in unresolved_programs()}
    states: list[ProgramSourceState] = []
    for item in resolved_programs():
        status, reason = _initial_status(item.program_id, core_ids, pending_ids)
        states.append(
            ProgramSourceState(
                item.program_id,
                item.title,
                item.official_url,
                status,
                0,
                reason,
                item.source_url_type,
                item.update_risk,
            )
        )
    return tuple(states)


# 判斷來源尚未請求前的狀態。
def _initial_status(
    program_id: str,
    core_ids: set[str],
    pending_ids: set[str],
) -> tuple[str, str]:
    if program_id in core_ids:
        return "core_covered", "已由六個核心來源監測，不重複請求。"
    if program_id in pending_ids:
        return "pending_source", "尚無可靠官方或正式機構轉載入口。"
    return "configured", "等待本次入口抓取。"


# 依抓取結果更新單一 URL 群組中的方案狀態。
def _update_program_states(
    states: dict[str, ProgramSourceState],
    programs: tuple[ScholarshipProgramWatch, ...],
    crawl: ListingCrawlResult,
    unique_counts: dict[str, int],
) -> None:
    for program in programs:
        count = unique_counts.get(program.program_id, 0)
        status, reason = _crawl_status(crawl, count)
        states[program.program_id] = ProgramSourceState(
            program.program_id,
            program.title,
            program.official_url,
            status,
            count,
            reason,
            _source_url_type(program),
            _source_risk(program),
        )


# 把抓取、候選與部分完成轉成可稽核狀態。
def _crawl_status(crawl: ListingCrawlResult, count: int) -> tuple[str, str]:
    if not crawl.pages:
        return "fetch_failed", "；".join(crawl.errors) or "入口頁未成功下載。"
    if count:
        status = "candidate_found"
        reason = "已找到唯一方案候選，將進入正文與公告分類。"
    else:
        status = "no_candidate"
        reason = "入口可讀，但本次未找到匹配候選。"
    if crawl.completeness == "partial":
        reason += f" 分頁部分完成：{crawl.stop_reason}。"
    return status, reason


# 建立整個 TUN 方案群組的來源診斷。
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


# 彙整未解決、部分完成與抓取失敗原因。
def _diagnostic_error(
    unresolved_count: int,
    partial: list[tuple[str, ListingCrawlResult]],
    failed: list[tuple[str, ListingCrawlResult]],
) -> str:
    parts: list[str] = []
    if unresolved_count:
        parts.append(f"可靠入口待確認 {unresolved_count}")
    if partial:
        detail = "｜".join(_partial_detail(url, item) for url, item in partial[:8])
        parts.append(f"分頁未完整 {len(partial)}：{detail}")
    if failed:
        detail = "｜".join(
            f"{url}（{';'.join(item.errors)}）" for url, item in failed[:8]
        )
        parts.append(f"入口抓取失敗 {len(failed)}：{detail}")
    return "；".join(parts)


# 建立單一部分完成入口的摘要。
def _partial_detail(url: str, item: ListingCrawlResult) -> str:
    errors = "；".join(item.errors[:3])
    suffix = f"；{errors}" if errors else ""
    return f"{url}（{item.stop_reason}{suffix}）"


# 依完整性產生群組停止原因。
def _watch_stop_reason(completeness: str) -> str:
    if completeness == "incremental":
        return "program_watch_incremental_first_pages"
    if completeness == "complete":
        return "program_watch_all_detected_pages_completed"
    return "program_watch_partial"


# 將跨頁候選依內容雜湊去重。
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


# 對暫時性網路錯誤進行有限重試。
def _fetch_text_with_retry(client: DetailSafeHttpClient, url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(_FETCH_ATTEMPTS):
        try:
            return client.get_text(url)
        except (httpx.TimeoutException, httpx.TransportError) as error:
            last_error = error
            if attempt + 1 < _FETCH_ATTEMPTS:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


# 將外部錯誤壓縮成診斷文字。
def _error_text(error: Exception) -> str:
    return " ".join(str(error).split())[:120] or type(error).__name__


# 同一入口的多個方案只請求一次。
def _group_programs_by_url(
    programs: tuple[ScholarshipProgramWatch, ...],
) -> dict[str, tuple[ScholarshipProgramWatch, ...]]:
    grouped: dict[str, list[ScholarshipProgramWatch]] = defaultdict(list)
    for program in programs:
        grouped[program.official_url].append(program)
    return {url: tuple(items) for url, items in grouped.items()}


# 保留既有測試介面並回傳原始節點命中數。
def _extract_program_notices(
    html: str,
    official_url: str,
    programs: tuple[ScholarshipProgramWatch, ...],
) -> tuple[list[Scholarship], int]:
    records, matched, _ = _extract_program_notices_with_counts(
        html,
        official_url,
        official_url,
        programs,
    )
    return records, matched


# 從單頁找出方案候選並計算每項唯一公告數。
def _extract_program_notices_with_counts(
    html: str,
    page_url: str,
    entry_url: str,
    programs: tuple[ScholarshipProgramWatch, ...],
) -> tuple[list[Scholarship], int, dict[str, int]]:
    soup = BeautifulSoup(html, "html.parser")
    for unwanted in soup.select("script, style, noscript, svg"):
        unwanted.decompose()

    records: list[Scholarship] = []
    raw_node_matches = 0
    program_counts: dict[str, int] = defaultdict(int)
    seen: set[str] = set()
    for node in soup.select(_CANDIDATE_SELECTORS):
        context = _candidate_context(node)
        if not context:
            continue
        date_context = _candidate_date_context(node)
        for program in programs:
            match = match_program(context, program)
            if not match.matched:
                continue
            raw_node_matches += 1
            record = _candidate_record(
                node,
                page_url,
                entry_url,
                program,
                match,
                date_context,
            )
            if record is None:
                continue
            key = f"{program.program_id}|{record.published_date}|{record.source_url}"
            if key in seen:
                continue
            seen.add(key)
            program_counts[program.program_id] += 1
            records.append(record)
    return records, raw_node_matches, dict(program_counts)


# 依 URL 類型判斷入口頁本身是否可作為候選。
def _candidate_record(
    node: Tag,
    page_url: str,
    entry_url: str,
    program: ScholarshipProgramWatch,
    match: ProgramMatchResult,
    date_context: str,
) -> Scholarship | None:
    source_url = _candidate_url(node, page_url)
    published_date = _extract_date(node, date_context) or ""
    direct_allowed = allows_direct_candidate(_source_url_type(program))
    if not published_date and source_url == page_url and not direct_allowed:
        return None
    return _build_scholarship(
        program,
        _candidate_title(node, program),
        published_date,
        source_url,
        entry_url,
        match,
    )


# 建立標準 Scholarship 候選。
def _build_scholarship(
    program: ScholarshipProgramWatch,
    title: str,
    published_date: str,
    source_url: str,
    entry_url: str,
    match: ProgramMatchResult,
) -> Scholarship:
    return Scholarship.from_raw(
        f"tun-program-{program.program_id}",
        title,
        published_date,
        source_url,
        program_id=program.program_id,
        entry_url=entry_url,
        detail_url=source_url,
        match_method=match.method,
        match_score=match.score,
        matched_alias=match.matched_alias,
    )


# 優先使用連結標題，避免容器其他文字造成誤命中。
def _candidate_context(node: Tag) -> str:
    link = _primary_link(node)
    if isinstance(link, Tag):
        title_text = " ".join(link.get_text(" ", strip=True).split())
        if len(title_text) >= _MIN_TITLE_CONTEXT_LENGTH:
            return title_text[:400]
    return _candidate_date_context(node)


# 取得候選附近的日期與摘要文字。
def _candidate_date_context(node: Tag) -> str:
    if node.name == "a":
        container = node.find_parent(("article", "li", "tr")) or node.parent or node
    else:
        container = node.find_parent("article") or node
    return " ".join(container.get_text(" ", strip=True).split())[:1200]


# 取得候選節點中的主要連結。
def _primary_link(node: Tag) -> Tag | None:
    if node.name == "a":
        return node
    link = node.find("a", href=True)
    return link if isinstance(link, Tag) else None


# 取得候選公告標題。
def _candidate_title(node: Tag, program: ScholarshipProgramWatch) -> str:
    link = _primary_link(node)
    if isinstance(link, Tag):
        text = " ".join(link.get_text(" ", strip=True).split())
        if len(text) >= 4:
            return text[:220]
    return program.title


# 解析相對連結並排除不可導覽的 scheme。
def _candidate_url(node: Tag, official_url: str) -> str:
    link = _primary_link(node)
    if isinstance(link, Tag):
        href = str(link.get("href", "")).strip()
        if href and not href.lower().startswith(("javascript:", "mailto:", "tel:")):
            return urljoin(official_url, href)
    return official_url


# 保留既有測試介面；正式流程使用可解釋 matcher。
def _matches_program(text: str, program: ScholarshipProgramWatch) -> bool:
    return match_program(text, program).matched


# 取得解析後的 URL 類型；舊測試資料預設視為列表。
def _source_url_type(program: ScholarshipProgramWatch) -> SourceUrlType:
    value = getattr(program, "source_url_type", SourceUrlType.LIST)
    return SourceUrlType(value)


# 取得跨年度風險；舊測試資料預設為中等。
def _source_risk(program: ScholarshipProgramWatch) -> SourceRisk:
    value = getattr(program, "update_risk", SourceRisk.MEDIUM)
    return SourceRisk(value)


# 解析 time 屬性或候選周邊的民國／西元日期。
def _extract_date(node: Tag, context: str) -> str | None:
    time_node = node.find("time") if node.name != "time" else node
    if isinstance(time_node, Tag):
        datetime_value = str(time_node.get("datetime", "")).strip()
        parsed = _parse_date(datetime_value)
        if parsed is not None:
            return parsed.isoformat()
    parsed = _parse_date(context)
    return parsed.isoformat() if parsed is not None else None


# 將民國或西元日期轉成 date。
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
