# -*- coding: utf-8 -*-

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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
    resolved_programs,
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
_FETCH_ATTEMPTS = 3
_MIN_ALIAS_MATCH_LENGTH = 4
_MIN_TITLE_CONTEXT_LENGTH = 6
_EQUIVALENT_TERMS = (
    ("大專院校", "大專校院"),
    ("臺北", "台北"),
    ("獎助金", "獎助學金"),
    ("獎勵學金", "獎學金"),
)


@dataclass(frozen=True)
class ProgramSourceState:
    """單一 TUN 方案在本次執行中的來源與候選狀態。"""

    program_id: str
    title: str
    entry_url: str
    status: str
    candidate_count: int = 0
    reason: str = ""


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
        raw_matches = 0
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
            match_counts: dict[str, int] = defaultdict(int)
            for page in crawl.pages:
                found, matched, page_counts = _extract_program_notices_with_counts(
                    page.html,
                    page.url,
                    official_url,
                    programs,
                )
                raw_matches += matched
                for program_id, count in page_counts.items():
                    match_counts[program_id] += count
                _append_unique(records, seen_records, found)
            _update_program_states(states, programs, crawl, match_counts)

        self.program_states = tuple(states[item.program_id] for item in resolved_programs())
        self.diagnostic = _build_diagnostic(
            crawls,
            len(records),
            raw_matches,
            successful_programs,
            fetcher.fallback_used,
        )
        return records

    # 逐方案輸出狀態，確保 38 項都有明確結果而不是只看群組總數。
    def program_status_lines(self) -> list[str]:
        return [
            f"TUN方案 {item.program_id}：{item.status}；候選 {item.candidate_count}；"
            f"入口 {item.entry_url or '由核心來源涵蓋'}"
            + (f"；{item.reason}" if item.reason else "")
            for item in self.program_states
        ]


class _ProgramPageFetcher:
    """每個工作執行緒重用一個 HTTP client，降低 TLS 與連線壓力。"""

    def __init__(self, timeout_seconds: float, user_agent: str, workers: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.workers = workers
        self.fallback_used = False

    # 入口頁及 next-only 頁面維持單頁下載。
    def fetch_one(self, url: str) -> str:
        with DetailSafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            html = _fetch_text_with_retry(client, url)
            self.fallback_used = self.fallback_used or bool(client.fallback_hosts)
            return html

    # URL 分塊後平行處理；每塊內循序並共用同一個 HTTP client。
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

    # 單一工作執行緒只建立一次 client，逐頁重用 keep-alive 連線。
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


# 以輪詢方式分配 URL，讓前後頁平均散佈於各工作執行緒。
def _chunk_urls(urls: tuple[str, ...], workers: int) -> tuple[tuple[str, ...], ...]:
    worker_count = min(workers, len(urls))
    return tuple(tuple(urls[index::worker_count]) for index in range(worker_count))


# 建立 38 項方案的初始狀態。
def _initial_program_states() -> tuple[ProgramSourceState, ...]:
    core_ids = {item.program_id for item in core_covered_programs()}
    pending_ids = {item.program_id for item in unresolved_programs()}
    states: list[ProgramSourceState] = []
    for item in resolved_programs():
        if item.program_id in core_ids:
            status = "core_covered"
            reason = "已由六個核心來源監測，不重複請求。"
        elif item.program_id in pending_ids:
            status = "pending_source"
            reason = "尚無可靠官方或正式機構轉載入口。"
        else:
            status = "configured"
            reason = "等待本次入口抓取。"
        states.append(
            ProgramSourceState(
                item.program_id,
                item.title,
                item.official_url,
                status,
                0,
                reason,
            )
        )
    return tuple(states)


# 依入口抓取與匹配結果更新同一網址下的所有方案狀態。
def _update_program_states(
    states: dict[str, ProgramSourceState],
    programs: tuple[ScholarshipProgramWatch, ...],
    crawl: ListingCrawlResult,
    match_counts: dict[str, int],
) -> None:
    for program in programs:
        count = match_counts.get(program.program_id, 0)
        if not crawl.pages:
            status = "fetch_failed"
            reason = "；".join(crawl.errors) or "入口頁未成功下載。"
        elif count:
            status = "candidate_found"
            reason = "已找到方案候選，將進入正文與公告分類。"
        else:
            status = "no_candidate"
            reason = "入口可讀，但本次未找到匹配候選。"
        if crawl.completeness == "partial" and crawl.pages:
            reason += f" 分頁部分完成：{crawl.stop_reason}。"
        states[program.program_id] = ProgramSourceState(
            program.program_id,
            program.title,
            program.official_url,
            status,
            count,
            reason,
        )


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


# 建立 partial 的網址、停止原因與前三筆實際失敗頁。
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


# 將 partial 原因及最多三個錯誤壓縮成單站診斷。
def _partial_detail(url: str, item: ListingCrawlResult) -> str:
    errors = "；".join(item.errors[:3])
    suffix = f"；{errors}" if errors else ""
    return f"{url}（{item.stop_reason}{suffix}）"


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
    """只對 timeout／transport error 進行兩次有限重試。"""

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


def _error_text(error: Exception) -> str:
    return " ".join(str(error).split())[:120] or type(error).__name__


def _group_programs_by_url(
    programs: tuple[ScholarshipProgramWatch, ...],
) -> dict[str, tuple[ScholarshipProgramWatch, ...]]:
    grouped: dict[str, list[ScholarshipProgramWatch]] = defaultdict(list)
    for program in programs:
        grouped[program.official_url].append(program)
    return {url: tuple(items) for url, items in grouped.items()}


# 保留既有測試介面，同時由內部版本回報各 program 的匹配數。
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
    matched_count = 0
    program_counts: dict[str, int] = defaultdict(int)
    seen: set[str] = set()
    for node in soup.select(_CANDIDATE_SELECTORS):
        context = _candidate_context(node)
        if not context:
            continue
        date_context = _candidate_date_context(node)
        for program in programs:
            if not _matches_program(context, program):
                continue
            matched_count += 1
            program_counts[program.program_id] += 1
            source_url = _candidate_url(node, page_url)
            published_date = _extract_date(node, date_context) or ""
            if not published_date and source_url == page_url:
                continue
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
                    program_id=program.program_id,
                    entry_url=entry_url,
                    detail_url=source_url,
                )
            )
    return records, matched_count, dict(program_counts)


# 有實質連結標題時只用標題做方案比對，避免整個容器文字造成誤觸。
def _candidate_context(node: Tag) -> str:
    link = _primary_link(node)
    if isinstance(link, Tag):
        title_text = " ".join(link.get_text(" ", strip=True).split())
        if len(title_text) >= _MIN_TITLE_CONTEXT_LENGTH:
            return title_text[:400]
    return _candidate_date_context(node)


# 日期仍使用完整公告列／文章容器，避免標題優先後遺失旁邊日期。
def _candidate_date_context(node: Tag) -> str:
    if node.name == "a":
        container = node.find_parent(("article", "li", "tr")) or node.parent or node
    else:
        container = node.find_parent("article") or node
    return " ".join(container.get_text(" ", strip=True).split())[:1200]


# 取得節點自身或其第一個公告連結。
def _primary_link(node: Tag) -> Tag | None:
    if node.name == "a":
        return node
    link = node.find("a", href=True)
    return link if isinstance(link, Tag) else None


def _candidate_title(node: Tag, program: ScholarshipProgramWatch) -> str:
    link = _primary_link(node)
    if isinstance(link, Tag):
        text = " ".join(link.get_text(" ", strip=True).split())
        if len(text) >= 4:
            return text[:220]
    return program.title


def _candidate_url(node: Tag, official_url: str) -> str:
    link = _primary_link(node)
    if isinstance(link, Tag):
        href = str(link.get("href", "")).strip()
        if href and not href.lower().startswith(("javascript:", "mailto:", "tel:")):
            return urljoin(official_url, href)
    return official_url


def _matches_program(text: str, program: ScholarshipProgramWatch) -> bool:
    normalized = _normalize(text)
    aliases = (_normalize(alias) for alias in program.aliases)
    return any(
        len(alias) >= _MIN_ALIAS_MATCH_LENGTH and alias in normalized
        for alias in aliases
    )


# 只使用受控等價詞，避免任意模糊比對造成不同方案誤合併。
def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    for source, target in _EQUIVALENT_TERMS:
        value = value.replace(source, target)
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
