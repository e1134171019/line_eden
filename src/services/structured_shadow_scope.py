# -*- coding: utf-8 -*-

import re

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.evaluators.runtime_safety import EXPIRED, classify_application_period

_ROC_YEAR_PATTERN = re.compile(r"(?<!\d)(?P<year>1\d{2})年")
_GREGORIAN_YEAR_PATTERN = re.compile(r"(?<!\d)(?P<year>20\d{2})(?!\d)")


def structured_shadow_skip_status(
    title: str,
    fetch_result: DetailFetchResult,
) -> str | None:
    """已截止公告不執行 structured shadow，避免歷史資料消耗額度。"""
    published_hint = _published_date_hint(title)
    period = classify_application_period(
        fetch_result.eligibility_text(),
        published_hint,
    )
    return EXPIRED if period.status == EXPIRED else None


def _published_date_hint(title: str) -> str:
    roc_match = _ROC_YEAR_PATTERN.search(title)
    if roc_match:
        year = int(roc_match.group("year")) + 1911
        return f"{year:04d}-01-01"
    gregorian_match = _GREGORIAN_YEAR_PATTERN.search(title)
    if gregorian_match:
        year = int(gregorian_match.group("year"))
        return f"{year:04d}-01-01"
    return ""
