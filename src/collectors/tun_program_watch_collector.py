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
    ProgramSourceType,
    ScholarshipProgramWatch,
)
from src.catalogs.tun_program_sources import (
    core_covered_programs,
    monitorable_programs,
    resolved_programs,
    unresolved_programs,
)
from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import (
    CollectionMode,
    CollectorDiagnostic,
    RejectionReasonCount,
    SourceAccessMode,
    SourceTargetDiagnostic,
)
from src.collectors.http_client import DetailSafeHttpClient, SafeHttpClient
from src.collectors.listing_paginator import ListingCrawlResult
from src.collectors.program_entry_crawler import (
    FetchMany,
    FetchText,
    select_program_entry_crawler,
)
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
_IGNORED_HREF_MARKERS = (
    "addtoany.com/",
    "facebook.com/sharer",
    "line.me/r/msg",
    "twitter.com/intent",
    "mailto:",
    "javascript:",
    "tel:",
)

@dataclass(frozen=True)
class _ProgramMatchCount:
    """記錄單一頁面上一個方案的命中與解析數。"""

    program_id: str
    raw_matches: int
    parsed_rows: int


@dataclass(frozen=True)
class _ProgramPageExtraction:
    """封裝一頁方案公告與逐方案解析統計。"""

    records: tuple[Scholarship, ...]
    program_counts: tuple[_ProgramMatchCount, ...]


class TunProgramWatchCollector(BaseCollector):
    """監測 30 項方案；完整稽核有限併發翻頁，每日只抓入口頁。"""

    source_label = "TUN 30方案官方監測"
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
        self.core_evidence: tuple[Scholarship, ...] = tuple()

    def load_core_evidence(self, notices: tuple[Scholarship, ...]) -> None:
        """副作用函式：載入前序核心來源公告，供涵蓋方案逐項核對。"""

        self.core_evidence = notices

    def collect(self) -> list[Scholarship]:
        groups = _group_programs_by_url(monitorable_programs())
        records: list[Scholarship] = []
        seen_records: set[str] = set()
        crawls: list[tuple[str, ListingCrawlResult]] = []
        raw_matches = 0
        duplicate_rows = 0
        raw_matches_by_program: dict[str, int] = defaultdict(int)
        fetcher = _ProgramPageFetcher(
            self.timeout_seconds,
            self.user_agent,
            self.fetch_workers,
        )

        for official_url, programs in groups.items():
            crawl = _crawl_program_entry(
                official_url,
                programs[0].source_type,
                self.collection_mode,
                self.max_pages,
                fetcher.fetch_one,
                fetcher.fetch_many,
            )
            crawls.append((official_url, crawl))
            for page in crawl.pages:
                extraction = _extract_program_source_diagnostics(
                    page.html,
                    page.url,
                    programs,
                )
                for count in extraction.program_counts:
                    raw_matches += count.raw_matches
                    raw_matches_by_program[count.program_id] += count.raw_matches
                duplicate_rows += _append_unique(
                    records,
                    seen_records,
                    list(extraction.records),
                )

        target_diagnostics = _build_target_diagnostics(
            crawls,
            raw_matches_by_program,
            records,
            self.core_evidence,
        )
        successful_programs = sum(target.is_succeeded for target in target_diagnostics)
        self.diagnostic = _build_diagnostic(
            crawls,
            len(records),
            raw_matches,
            successful_programs,
            fetcher.fallback_used,
            target_diagnostics,
            duplicate_rows,
        )
        return records


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


# 彙整所有入口分頁結果，完整模式若任一網站缺頁即標示 partial。
def _build_diagnostic(
    crawls: list[tuple[str, ListingCrawlResult]],
    parsed_rows: int,
    raw_rows: int,
    successful_programs: int,
    fallback_used: bool,
    target_diagnostics: tuple[SourceTargetDiagnostic, ...] = tuple(),
    duplicate_rows: int = 0,
) -> CollectorDiagnostic:
    unresolved_count = len(unresolved_programs())
    partial = [(url, item) for url, item in crawls if item.completeness == "partial"]
    failed = [(url, item) for url, item in crawls if not item.pages]
    failed_targets = tuple(
        target for target in target_diagnostics if not target.is_succeeded
    )
    mode = crawls[0][1].completeness if crawls else "unknown"
    completeness = "incremental" if mode == "incremental" else "complete"
    if unresolved_count or partial or failed or (
        failed_targets and mode != "incremental"
    ):
        completeness = "partial"
    verified_programs = (
        sum(target.is_succeeded for target in target_diagnostics)
        if target_diagnostics
        else successful_programs
    )
    rejected_rows = max(raw_rows - parsed_rows - duplicate_rows, 0)
    rejection_reasons = (
        (RejectionReasonCount("命中方案名稱但未建立可追蹤公告", rejected_rows),)
        if rejected_rows
        else tuple()
    )
    return CollectorDiagnostic(
        completeness=completeness,
        pages_detected=sum(item.pages_detected for _, item in crawls),
        pages_requested=sum(item.pages_requested for _, item in crawls),
        pages_succeeded=sum(item.pages_succeeded for _, item in crawls),
        raw_rows=raw_rows,
        parsed_rows=parsed_rows,
        rejected_rows=rejected_rows,
        duplicate_rows=duplicate_rows,
        rejection_reasons=rejection_reasons,
        stop_reason=_watch_stop_reason(completeness),
        error=_diagnostic_error(unresolved_count, partial, failed, failed_targets),
        ssl_compatibility_fallback=fallback_used,
        child_sources_detected=len(TUN_2025_PROGRAMS),
        child_sources_succeeded=verified_programs,
        target_diagnostics=target_diagnostics,
    )


def _build_target_diagnostics(
    crawls: list[tuple[str, ListingCrawlResult]],
    raw_matches_by_program: dict[str, int],
    records: list[Scholarship],
    core_evidence: tuple[Scholarship, ...] = tuple(),
) -> tuple[SourceTargetDiagnostic, ...]:
    """純函式：建立 30 個方案各自的入口與抓取診斷。"""

    crawl_by_url = {url: crawl for url, crawl in crawls}
    parsed_by_program: dict[str, int] = defaultdict(int)
    for scholarship in records:
        program_id = scholarship.source.removeprefix("tun-program-")
        parsed_by_program[program_id] += 1
    direct_ids = {program.program_id for program in monitorable_programs()}
    covered_ids = {program.program_id for program in core_covered_programs()}
    return tuple(
        _program_target(
            program,
            crawl_by_url.get(program.official_url),
            raw_matches_by_program.get(program.program_id, 0),
            parsed_by_program.get(program.program_id, 0),
            direct_ids,
            covered_ids,
            core_evidence,
        )
        for program in resolved_programs()
    )


def _program_target(
    program: ScholarshipProgramWatch,
    crawl: ListingCrawlResult | None,
    raw_rows: int,
    parsed_rows: int,
    direct_ids: set[str],
    covered_ids: set[str],
    core_evidence: tuple[Scholarship, ...],
) -> SourceTargetDiagnostic:
    """純函式：建立一個 TUN 邏輯方案的來源診斷。"""

    if program.program_id in covered_ids:
        return _core_covered_program_target(program, core_evidence)
    if program.program_id not in direct_ids:
        return SourceTargetDiagnostic(
            program.program_id,
            program.title,
            SourceAccessMode.PENDING,
            completeness="pending",
            error="可靠入口待確認",
        )
    return _direct_program_target(program, crawl, raw_rows, parsed_rows)


def _core_covered_program_target(
    program: ScholarshipProgramWatch,
    core_evidence: tuple[Scholarship, ...],
) -> SourceTargetDiagnostic:
    """純函式：核心來源必須真的命中方案名稱，不能只靠設定宣告成功。"""

    matches = sum(_matches_program(notice.title, program) for notice in core_evidence)
    completeness = "covered" if matches else "partial"
    error = "" if matches else "核心來源公告未命中方案別名"
    return SourceTargetDiagnostic(
        program.program_id,
        program.title,
        SourceAccessMode.CORE_COVERED,
        completeness=completeness,
        raw_rows=matches,
        parsed_rows=matches,
        error=error,
    )


def _direct_program_target(
    program: ScholarshipProgramWatch,
    crawl: ListingCrawlResult | None,
    raw_rows: int,
    parsed_rows: int,
) -> SourceTargetDiagnostic:
    """純函式：將直接監測方案與共用入口 crawl 結果合併。"""

    completeness, semantic_error = _semantic_target_status(crawl, raw_rows, parsed_rows)
    crawl_error = "；".join(crawl.errors) if crawl else "入口未建立 crawl 診斷"
    errors = "；".join(value for value in (crawl_error, semantic_error) if value)
    return SourceTargetDiagnostic(
        target_id=program.program_id,
        display_name=program.title,
        access_mode=SourceAccessMode.DIRECT,
        entry_url=program.official_url,
        completeness=completeness,
        pages_detected=crawl.pages_detected if crawl else None,
        pages_requested=crawl.pages_requested if crawl else 0,
        pages_succeeded=crawl.pages_succeeded if crawl else 0,
        raw_rows=raw_rows,
        parsed_rows=parsed_rows,
        rejected_rows=max(raw_rows - parsed_rows, 0),
        error=errors,
    )


def _semantic_target_status(
    crawl: ListingCrawlResult | None,
    raw_rows: int,
    parsed_rows: int,
) -> tuple[str, str]:
    """純函式：頁面成功之外，方案名稱與公告列也必須實際命中。"""

    if crawl is None or not crawl.pages:
        return "failed", "入口抓取失敗"
    if raw_rows == 0:
        return "partial", "入口可連線但未命中方案別名"
    if parsed_rows == 0:
        return "partial", "命中方案名稱但未建立可追蹤公告"
    return crawl.completeness, ""


# 建立 partial 的網址、停止原因與前三筆實際失敗頁。
def _diagnostic_error(
    unresolved_count: int,
    partial: list[tuple[str, ListingCrawlResult]],
    failed: list[tuple[str, ListingCrawlResult]],
    failed_targets: tuple[SourceTargetDiagnostic, ...] = tuple(),
) -> str:
    parts: list[str] = []
    if unresolved_count:
        parts.append(f"可靠入口待確認 {unresolved_count}")
    if partial:
        detail = "｜".join(_partial_detail(url, item) for url, item in partial[:8])
        parts.append(f"分頁未完整 {len(partial)}：{detail}")
    if failed:
        detail = "｜".join(f"{url}（{';'.join(item.errors)}）" for url, item in failed[:8])
        parts.append(f"入口抓取失敗 {len(failed)}：{detail}")
    if failed_targets:
        names = "、".join(target.display_name for target in failed_targets[:8])
        parts.append(f"方案語意驗證未通過 {len(failed_targets)}：{names}")
    return "；".join(parts)


# 將 partial 原因及最多三個錯誤壓縮成單站診斷。
def _partial_detail(url: str, item: ListingCrawlResult) -> str:
    errors = "；".join(item.errors[:3])
    suffix = f"；{errors}" if errors else ""
    return f"{url}（{item.stop_reason}{suffix}）"


def _watch_stop_reason(completeness: str) -> str:
    if completeness == "incremental":
        return "program_watch_incremental_catchup_pages"
    if completeness == "complete":
        return "program_watch_all_detected_pages_completed"
    return "program_watch_partial"


# 依內容雜湊合併跨頁重複公告。
def _append_unique(
    records: list[Scholarship],
    seen_records: set[str],
    found: list[Scholarship],
) -> int:
    duplicate_rows = 0
    for item in found:
        if item.announcement_id in seen_records:
            duplicate_rows += 1
            continue
        seen_records.add(item.announcement_id)
        records.append(item)
    return duplicate_rows


def _fetch_text_with_retry(client: SafeHttpClient, url: str) -> str:
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


def _crawl_program_entry(
    entry_url: str,
    source_type: ProgramSourceType,
    collection_mode: CollectionMode,
    max_pages: int,
    fetch_text: FetchText,
    fetch_many: FetchMany,
) -> ListingCrawlResult:
    """副作用函式：依來源型態選擇列表翻頁或單頁內容監測。"""

    crawler = select_program_entry_crawler(source_type)
    return crawler.fetch_pages(
        entry_url,
        collection_mode,
        max_pages,
        fetch_text,
        fetch_many,
    )


def _extract_program_source_diagnostics(
    html: str,
    entry_url: str,
    programs: tuple[ScholarshipProgramWatch, ...],
) -> _ProgramPageExtraction:
    """純函式：依來源契約選擇列表公告或固定頁快照解析。"""

    if programs[0].source_type is ProgramSourceType.LISTING:
        return _extract_program_notice_diagnostics(html, entry_url, programs)
    return _extract_fixed_program_diagnostics(html, entry_url, programs)


def _extract_fixed_program_diagnostics(
    html: str,
    entry_url: str,
    programs: tuple[ScholarshipProgramWatch, ...],
) -> _ProgramPageExtraction:
    """純函式：固定頁命中方案後建立穩定公告，交由修訂快照追蹤內容。"""

    soup = BeautifulSoup(html, "html.parser")
    for unwanted in soup.select("script, style, noscript, svg"):
        unwanted.decompose()
    page_text = " ".join(soup.get_text(" ", strip=True).split())
    parsed_date = _parse_date(page_text)
    published_date = parsed_date.isoformat() if parsed_date else ""
    records: list[Scholarship] = []
    counts: list[_ProgramMatchCount] = []
    for program in programs:
        has_program = _matches_program(page_text, program)
        parsed_rows = int(has_program)
        counts.append(_ProgramMatchCount(program.program_id, parsed_rows, parsed_rows))
        if has_program:
            records.append(
                Scholarship.from_raw(
                    f"tun-program-{program.program_id}",
                    program.title,
                    published_date,
                    entry_url,
                )
            )
    return _ProgramPageExtraction(tuple(records), tuple(counts))


def _extract_program_notices(  # pyright: ignore[reportUnusedFunction]
    html: str,
    official_url: str,
    programs: tuple[ScholarshipProgramWatch, ...],
) -> tuple[list[Scholarship], int]:
    """純函式：保留既有解析介面並回傳整頁命中總數。"""

    extraction = _extract_program_notice_diagnostics(html, official_url, programs)
    matched_count = sum(count.raw_matches for count in extraction.program_counts)
    return list(extraction.records), matched_count


def _extract_program_notice_diagnostics(
    html: str,
    official_url: str,
    programs: tuple[ScholarshipProgramWatch, ...],
) -> _ProgramPageExtraction:
    """純函式：解析公告並保留逐方案命中與成功列數。"""

    soup = BeautifulSoup(html, "html.parser")
    for unwanted in soup.select("script, style, noscript, svg"):
        unwanted.decompose()

    records: list[Scholarship] = []
    matched_counts: dict[str, int] = defaultdict(int)
    parsed_counts: dict[str, int] = defaultdict(int)
    seen: set[str] = set()
    for node in soup.select(_CANDIDATE_SELECTORS):
        context = _candidate_context(node)
        if not context:
            continue
        date_context = _candidate_date_context(node)
        for program in programs:
            if not _matches_program(context, program):
                continue
            matched_counts[program.program_id] += 1
            published_date = _extract_date(node, date_context)
            if published_date is None:
                continue
            source_url = _candidate_url(node, official_url)
            title = _candidate_title(node, program)
            key = f"{program.program_id}|{published_date}|{source_url}"
            if key in seen:
                continue
            seen.add(key)
            parsed_counts[program.program_id] += 1
            records.append(
                Scholarship.from_raw(
                    f"tun-program-{program.program_id}",
                    title,
                    published_date,
                    source_url,
                )
            )
    counts = tuple(
        _ProgramMatchCount(
            program.program_id,
            matched_counts[program.program_id],
            parsed_counts[program.program_id],
        )
        for program in programs
    )
    return _ProgramPageExtraction(tuple(records), counts)


# 有實質連結標題時只用標題做方案比對，避免整個容器文字造成誤觸。
def _candidate_context(node: Tag) -> str:
    link = _primary_link(node)
    if isinstance(link, Tag):
        title_text = " ".join(link.get_text(" ", strip=True).split())
        if len(title_text) >= _MIN_TITLE_CONTEXT_LENGTH:
            return title_text[:400]
        if node.name == "a":
            return ""
    if node.name == "a":
        return ""
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
        return node if _is_notice_link(node) else None
    return next(
        (
            link
            for link in node.find_all("a", href=True)
            if _is_notice_link(link)
        ),
        None,
    )


def _is_notice_link(link: Tag) -> bool:
    """純函式：排除分享、通訊與腳本連結，只留下可能的公告資源。"""

    href = str(link.get("href", "")).strip().casefold()
    return bool(href) and not any(marker in href for marker in _IGNORED_HREF_MARKERS)


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
