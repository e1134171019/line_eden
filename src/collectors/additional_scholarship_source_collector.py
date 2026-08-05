# -*- coding: utf-8 -*-

from datetime import date
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.catalogs.additional_source_catalog import AdditionalScholarshipSource
from src.collectors.base_collector import BaseCollector
from src.collectors.collection_diagnostics import CollectionMode, CollectorDiagnostic
from src.collectors.http_client import SafeHttpClient
from src.collectors.listing_paginator import crawl_listing_pages
from src.models.scholarship import Scholarship

_SCHOLARSHIP_MARKERS = (
    "獎助學金",
    "獎學金",
    "助學金",
    "獎助金",
    "獎勵學金",
    "助學計畫",
)
_IGNORED_SCHEMES = ("javascript:", "mailto:", "tel:")
_DATE_YMD = re.compile(
    r"(?P<year>20\d{2})\s*[./\-年]\s*(?P<month>\d{1,2})\s*[./\-月]\s*"
    r"(?P<day>\d{1,2})(?:\s*日)?"
)
_DATE_ROC = re.compile(
    r"(?<!\d)(?P<year>1\d{2})\s*[./\-年]\s*(?P<month>\d{1,2})\s*[./\-月]\s*"
    r"(?P<day>\d{1,2})(?:\s*日)?"
)
_URL_DATE = re.compile(r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)")


class AdditionalScholarshipSourceCollector(BaseCollector):
    """以共用分頁器監測新增官方方案頁與校外獎助公告入口。"""

    def __init__(
        self,
        config: AdditionalScholarshipSource,
        timeout_seconds: float,
        user_agent: str,
        collection_mode: CollectionMode,
        max_pages: int,
    ) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.collection_mode = collection_mode
        self.max_pages = min(max_pages, config.max_pages)
        self.diagnostic = CollectorDiagnostic()

    @property
    def source_label(self) -> str:
        return self.config.display_name

    def collect(self) -> list[Scholarship]:
        with SafeHttpClient(self.timeout_seconds, self.user_agent) as client:
            result = crawl_listing_pages(
                self.config.entry_url,
                self.collection_mode,
                self.max_pages,
                client.get_text,
            )
            fallback_used = bool(client.fallback_hosts)

        records: list[Scholarship] = []
        seen_urls: set[str] = set()
        raw_rows = 0
        for page in result.pages:
            page_records, page_rows = self._parse_html(page.html, page.url)
            raw_rows += page_rows
            for item in page_records:
                key = item.detail_url or item.source_url
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                records.append(item)

        if self.config.entry_title and self.config.entry_url not in seen_urls:
            records.insert(
                0,
                Scholarship.from_raw(
                    self.config.source_id,
                    self.config.entry_title,
                    "",
                    self.config.entry_url,
                    entry_url=self.config.entry_url,
                    detail_url=self.config.entry_url,
                ),
            )

        error = "; ".join(result.errors)
        self.diagnostic = CollectorDiagnostic(
            completeness=result.completeness,
            pages_detected=result.pages_detected,
            pages_requested=result.pages_requested,
            pages_succeeded=result.pages_succeeded,
            raw_rows=raw_rows,
            parsed_rows=len(records),
            rejected_rows=max(raw_rows - len(records), 0),
            stop_reason=result.stop_reason,
            error=error,
            ssl_compatibility_fallback=fallback_used,
        )
        if not records and error:
            raise RuntimeError(error)
        return records

    def _parse_html(self, html: str, page_url: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        raw_rows = 0
        for anchor in soup.find_all("a", href=True):
            raw_rows += 1
            if not isinstance(anchor, Tag):
                continue
            record = self._parse_anchor(anchor, page_url)
            if record is not None:
                records.append(record)
        return records, raw_rows

    def _parse_anchor(self, anchor: Tag, page_url: str) -> Scholarship | None:
        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith(("#", *_IGNORED_SCHEMES)):
            return None
        detail_url = urljoin(page_url, href)
        if not self._host_allowed(detail_url):
            return None

        title, context = _candidate_title_and_context(anchor)
        if not title or not _contains_scholarship_marker(title):
            return None
        if detail_url.rstrip("/") == page_url.rstrip("/") and not self.config.entry_title:
            return None

        published_date = _extract_date(context, detail_url)
        return Scholarship.from_raw(
            self.config.source_id,
            title,
            published_date,
            detail_url,
            entry_url=self.config.entry_url,
            detail_url=detail_url,
        )

    def _host_allowed(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(
            host == allowed.lower() or host.endswith(f".{allowed.lower()}")
            for allowed in self.config.allowed_hosts
        )


def _candidate_title_and_context(anchor: Tag) -> tuple[str, str]:
    anchor_text = _normalize_text(anchor.get_text(" ", strip=True))
    contexts = [anchor_text]
    parent: Tag | None = anchor
    for _ in range(3):
        candidate = parent.parent
        if not isinstance(candidate, Tag):
            break
        parent = candidate
        contexts.extend(
            normalized
            for text in parent.stripped_strings
            if (normalized := _normalize_text(text))
        )
        if parent.name in {"li", "tr", "article"}:
            break

    unique_contexts = list(dict.fromkeys(contexts))
    for text in unique_contexts:
        if _contains_scholarship_marker(text) and 4 <= len(text) <= 220:
            return text, " ".join(unique_contexts)
    return "", " ".join(unique_contexts)


def _contains_scholarship_marker(text: str) -> bool:
    return any(marker in text for marker in _SCHOLARSHIP_MARKERS)


def _extract_date(context: str, url: str) -> str:
    match = _DATE_YMD.search(context)
    if match:
        return _safe_iso_date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    match = _DATE_ROC.search(context)
    if match:
        return _safe_iso_date(
            int(match.group("year")) + 1911,
            int(match.group("month")),
            int(match.group("day")),
        )
    match = _URL_DATE.search(urlparse(url).path)
    if match:
        return _safe_iso_date(*(int(value) for value in match.groups()))
    return ""


def _safe_iso_date(year: int, month: int, day: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()
