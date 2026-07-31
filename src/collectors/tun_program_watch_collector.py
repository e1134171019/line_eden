# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import date
import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.catalogs.tun_2025_program_catalog import (
    TUN_2025_PROGRAMS,
    ScholarshipProgramWatch,
    pending_programs,
    verified_programs,
)
from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectorDiagnostic
from src.collectors.http_client import DetailSafeHttpClient
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


class TunProgramWatchCollector(BaseCollector):
    """監測 TUN 彙整的 38 項方案，但只採信已驗證的官方網站。"""

    source_label = "TUN 38方案官方監測"
    empty_is_healthy = True

    def __init__(self, timeout_seconds: float, user_agent: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.diagnostic = CollectorDiagnostic()

    def collect(self) -> list[Scholarship]:
        groups = _group_programs_by_url(verified_programs())
        records: list[Scholarship] = []
        seen_records: set[str] = set()
        pages_requested = 0
        pages_succeeded = 0
        successful_programs = 0
        raw_matches = 0
        failures: list[str] = []
        fallback_used = False

        with DetailSafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            for official_url, programs in groups.items():
                pages_requested += 1
                try:
                    html = client.get_text(official_url)
                except Exception as error:
                    program_ids = ",".join(item.program_id for item in programs)
                    message = " ".join(str(error).split())[:100]
                    failures.append(f"{program_ids}={official_url}（{message}）")
                    continue
                pages_succeeded += 1
                successful_programs += len(programs)
                found, matched = _extract_program_notices(html, official_url, programs)
                raw_matches += matched
                for item in found:
                    if item.content_hash in seen_records:
                        continue
                    seen_records.add(item.content_hash)
                    records.append(item)
            fallback_used = bool(client.fallback_hosts)

        pending_count = len(pending_programs())
        complete = pending_count == 0 and not failures
        error_parts: list[str] = []
        if pending_count:
            error_parts.append(f"官方入口待確認 {pending_count}")
        if failures:
            error_parts.append(
                f"官方頁面抓取失敗 {len(failures)}：" + "｜".join(failures)
            )
        self.diagnostic = CollectorDiagnostic(
            completeness="complete" if complete else "partial",
            pages_detected=len(groups),
            pages_requested=pages_requested,
            pages_succeeded=pages_succeeded,
            raw_rows=raw_matches,
            parsed_rows=len(records),
            rejected_rows=max(raw_matches - len(records), 0),
            stop_reason="program_watch_scan_completed",
            error="；".join(error_parts),
            ssl_compatibility_fallback=fallback_used,
            child_sources_detected=len(TUN_2025_PROGRAMS),
            child_sources_succeeded=successful_programs,
        )
        return records


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
