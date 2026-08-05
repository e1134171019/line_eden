# -*- coding: utf-8 -*-

from dataclasses import replace
from datetime import date
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.catalogs.tun_live_contracts import LiveSourceCandidate, live_contract
from src.catalogs.tun_program_sources import ResolvedProgramSource, resolved_programs
from src.collectors.collection_diagnostics import CollectionMode, CollectorDiagnostic
from src.collectors.http_client import DetailSafeHttpClient
from src.collectors.listing_paginator import ListingCrawlResult, crawl_listing_pages
from src.collectors.tun_program_watch_collector import (
    ProgramSourceState,
    TunProgramWatchCollector,
    _ProgramPageFetcher,
    _empty_group_diagnostic,
    _extract_program_notices_with_diagnostics,
    _merge_counts,
    _merge_discovery_diagnostics,
    _update_program_states,
)
from src.discovery.source_candidate_ranker import (
    SOURCE_GOVERNMENT,
    SOURCE_OFFICIAL,
    SOURCE_SCHOOL,
    RankedSourceCandidate,
)
from src.discovery.source_discovery_service import (
    ProgramDiscoveryRequest,
    ProgramSourceDiscoveryService,
)
from src.discovery.source_identity_validator import (
    SOURCE_VERIFIED,
    validate_source_identity,
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
_DISCOVERY_TRIGGER_STATUSES = frozenset((*_RETRYABLE_STATUSES, "no_current_announcement"))
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
    """主入口失敗時依序嘗試契約來源，完整稽核可再啟動公開來源發現。"""

    def __init__(
        self,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode = CollectionMode.INCREMENTAL,
        max_pages: int = 20,
        fetch_workers: int = 1,
        *,
        source_discovery: ProgramSourceDiscoveryService | None = None,
        source_discovery_min_score: int = 100,
        source_discovery_max_candidates: int = 5,
    ) -> None:
        super().__init__(
            timeout_seconds,
            user_agent,
            collection_mode,
            max_pages,
            fetch_workers,
        )
        if source_discovery_min_score < 1:
            raise ValueError("來源發現最低分數必須大於 0")
        if source_discovery_max_candidates < 1:
            raise ValueError("來源發現候選上限必須大於 0")
        self.source_discovery = source_discovery
        self.source_discovery_min_score = source_discovery_min_score
        self.source_discovery_max_candidates = source_discovery_max_candidates

    def collect(self) -> list[Scholarship]:
        records = super().collect()
        original_states = {item.program_id: item for item in self.program_states}
        source_by_id = {item.program_id: item for item in resolved_programs()}
        retry_stats = _RetryStats()

        for program_id, source in source_by_id.items():
            contract = live_contract(program_id)
            current = original_states[program_id]
            retryable = current.status in _RETRYABLE_STATUSES
            discoverable = self._can_discover(current.status)
            if not retryable and not contract.force_replace and not discoverable:
                continue
            if contract.force_replace:
                records = _replace_program_records(records, program_id, tuple(), True)
            attempt = self._retry_program(source, retry_stats)
            if attempt is None:
                continue
            original_states[program_id] = attempt.state
            if attempt.state.status == "matched":
                records = _replace_program_records(
                    records,
                    program_id,
                    attempt.records,
                    False,
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

    # 依 preferred、原入口、fallback 與公開搜尋候選順序嘗試，回傳最佳結果。
    def _retry_program(
        self,
        program: ResolvedProgramSource,
        stats: "_RetryStats",
    ) -> "_RetryAttempt | None":
        contract = live_contract(program.program_id)
        aliases = tuple(dict.fromkeys((*program.aliases, *contract.aliases)))
        variants = (
            _source_variants(program, contract.preferred_sources)
            if contract.use_catalog_sources
            else _source_variants(
                program,
                contract.preferred_sources,
                use_catalog_sources=False,
            )
        )
        best: _RetryAttempt | None = None
        attempted_urls: set[str] = set()
        for candidate in variants:
            attempted_urls.add(candidate.url)
            attempt = self._attempt_candidate(program, aliases, candidate, stats)
            if best is None or _attempt_score(attempt) > _attempt_score(best):
                best = attempt
            if attempt.state.status == "matched":
                return attempt
            if (
                attempt.state.status == "no_current_announcement"
                and not self._can_discover(attempt.state.status)
            ):
                return attempt

        for candidate in self._discovered_source_variants(
            program,
            aliases,
            attempted_urls,
        ):
            attempt = self._attempt_candidate(program, aliases, candidate, stats)
            if best is None or _attempt_score(attempt) > _attempt_score(best):
                best = attempt
            if attempt.state.status == "matched":
                return attempt
        return best

    def _attempt_candidate(
        self,
        program: ResolvedProgramSource,
        aliases: tuple[str, ...],
        candidate: LiveSourceCandidate,
        stats: "_RetryStats",
    ) -> "_RetryAttempt":
        variant = replace(
            program,
            aliases=aliases,
            official_url=candidate.url,
            source_url_type=candidate.source_url_type,
        )
        return self._collect_variant(variant, candidate.reason, stats)

    # 僅完整稽核在既有來源沒有當期公告或失敗時使用付費公開搜尋。
    def _can_discover(self, status: str) -> bool:
        return (
            self.source_discovery is not None
            and self.collection_mode is CollectionMode.FULL_AUDIT
            and status in _DISCOVERY_TRIGGER_STATUSES
        )

    # 搜尋摘要只負責排序；實際頁面必須再次下載並通過身分驗證。
    def _discovered_source_variants(
        self,
        program: ResolvedProgramSource,
        aliases: tuple[str, ...],
        attempted_urls: set[str],
    ) -> tuple[LiveSourceCandidate, ...]:
        if not self._can_discover("no_current_announcement"):
            return tuple()
        assert self.source_discovery is not None
        try:
            result = self.source_discovery.discover(
                ProgramDiscoveryRequest(
                    program.program_id,
                    program.title,
                    program.organizer,
                    aliases,
                    program.allowed_hosts,
                )
            )
        except Exception:
            return tuple()

        verified: list[LiveSourceCandidate] = []
        for candidate in result.candidates:
            if len(verified) >= self.source_discovery_max_candidates:
                break
            if candidate.score < self.source_discovery_min_score:
                continue
            url = candidate.hit.url
            if url in attempted_urls or _is_direct_document(url):
                continue
            if not self._verify_discovered_page(program, aliases, candidate):
                continue
            verified.append(
                LiveSourceCandidate(
                    url,
                    _discovered_url_type(candidate),
                    _discovery_reason(candidate),
                )
            )
        return tuple(verified)

    def _verify_discovered_page(
        self,
        program: ResolvedProgramSource,
        aliases: tuple[str, ...],
        candidate: RankedSourceCandidate,
    ) -> bool:
        try:
            with DetailSafeHttpClient(self.timeout_seconds, self.user_agent) as client:
                html = client.get_text(candidate.hit.url)
        except Exception:
            return False
        soup = BeautifulSoup(html, "html.parser")
        page_title = " ".join(
            (soup.title.get_text(" ", strip=True) if soup.title else "").split()
        )
        page_text = " ".join(soup.get_text(" ", strip=True).split())
        decision = validate_source_identity(
            candidate.hit.url,
            page_title,
            page_text,
            program.title,
            program.organizer,
            aliases,
            program.allowed_hosts,
        )
        return decision.status == SOURCE_VERIFIED

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


# preferred sources 優先；可依 live 契約停用舊 catalog 入口與 fallback。
def _source_variants(
    program: ResolvedProgramSource,
    preferred: tuple[LiveSourceCandidate, ...],
    *,
    use_catalog_sources: bool = True,
    current_year: int | None = None,
) -> tuple[LiveSourceCandidate, ...]:
    year = current_year if current_year is not None else date.today().year
    candidates = list(preferred)
    if use_catalog_sources:
        candidates.extend(
            [
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
        )
    unique: dict[str, LiveSourceCandidate] = {}
    for candidate in candidates:
        if candidate.url and _candidate_is_active(candidate, year):
            unique.setdefault(candidate.url, candidate)
    return tuple(unique.values())


# 年度單篇超過契約有效年後不得再當成目前公告候選。
def _candidate_is_active(candidate: LiveSourceCandidate, current_year: int) -> bool:
    valid_through = candidate.valid_through_year
    return valid_through is None or current_year <= valid_through


# 正式機構單篇 fallback 必須允許頁面自身成為候選。
def _fallback_url_type(url: str, default: SourceUrlType) -> SourceUrlType:
    host = urlparse(url).hostname or ""
    detail_markers = (
        "/p/404-",
        "/p/406-",
        "news_detail",
        "news_content",
        "announcement.php?aid=",
        "/posts/",
    )
    if any(marker in url for marker in detail_markers):
        if host.endswith(("edu.tw", "gov.tw")):
            return SourceUrlType.RELAY_DETAIL
        return SourceUrlType.ANNUAL_DETAIL
    return default


def _discovered_url_type(candidate: RankedSourceCandidate) -> SourceUrlType:
    if candidate.source_role in {SOURCE_GOVERNMENT, SOURCE_SCHOOL}:
        return SourceUrlType.RELAY_DETAIL
    if candidate.source_role == SOURCE_OFFICIAL:
        return SourceUrlType.ANNUAL_DETAIL
    return SourceUrlType.PENDING


def _discovery_reason(candidate: RankedSourceCandidate) -> str:
    reasons = "、".join(candidate.reasons)
    return f"runtime source discovery：score={candidate.score}；{reasons}"


def _is_direct_document(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".pdf", ".doc", ".docx", ".odt"))


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


# 同一 fallback 多個節點依 content hash 去重。
def _unique_records(records: list[Scholarship]) -> list[Scholarship]:
    unique: dict[str, Scholarship] = {}
    for item in records:
        unique.setdefault(item.content_hash, item)
    return list(unique.values())


# 以最後逐方案狀態重建群組成功數，不得掩蓋原本的分頁 partial。
def _rebuild_diagnostic(
    base: CollectorDiagnostic,
    states: tuple[ProgramSourceState, ...],
    stats: _RetryStats,
) -> CollectorDiagnostic:
    failures = [item for item in states if item.status in _RETRYABLE_STATUSES]
    completeness = "partial" if failures else base.completeness
    errors = "｜".join(
        f"{item.program_id}:{item.status}:{item.reason}" for item in failures[:10]
    )
    requested = base.pages_requested + stats.pages_requested
    succeeded = base.pages_succeeded + stats.pages_succeeded
    parsed = base.parsed_rows + stats.parsed_records
    raw = base.raw_rows + stats.raw_matches
    if failures:
        stop_reason = "program_watch_live_contract_partial"
    elif base.completeness in {"complete", "incremental"}:
        stop_reason = "program_watch_live_contract_passed"
    else:
        stop_reason = base.stop_reason
    return replace(
        base,
        completeness=completeness,
        pages_detected=(base.pages_detected or 0) + stats.pages_detected,
        pages_requested=requested,
        pages_succeeded=succeeded,
        raw_rows=raw,
        parsed_rows=parsed,
        rejected_rows=max(raw - parsed, 0),
        stop_reason=stop_reason,
        error=errors or base.error,
        ssl_compatibility_fallback=(
            base.ssl_compatibility_fallback or stats.ssl_fallback
        ),
        child_sources_detected=len(states),
        child_sources_succeeded=len(states) - len(failures),
    )
