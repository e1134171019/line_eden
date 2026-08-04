# -*- coding: utf-8 -*-

from dataclasses import dataclass
from urllib.parse import urlparse

SOURCE_VERIFIED = "verified"
SOURCE_REVIEW = "review"
SOURCE_REJECTED = "rejected"


@dataclass(frozen=True)
class SourceIdentityDecision:
    """網頁下載後的主辦單位與方案身分驗證結果。"""

    status: str
    organizer_match: bool
    program_match: bool
    trusted_host: bool
    reasons: tuple[str, ...]


# 官方網域可省略主辦單位文字；正式轉載必須同時命中方案與主辦單位。
def validate_source_identity(
    url: str,
    page_title: str,
    page_text: str,
    program_title: str,
    organizer: str,
    aliases: tuple[str, ...] = tuple(),
    official_hosts: tuple[str, ...] = tuple(),
) -> SourceIdentityDecision:
    host = (urlparse(url).hostname or "").lower()
    trusted = _trusted_host(host, official_hosts)
    text = _compact(f"{page_title} {page_text}")
    program_match = any(
        _compact(name) in text
        for name in dict.fromkeys((program_title, *aliases))
        if name.strip()
    )
    organizer_match = bool(organizer and _compact(organizer) in text)
    reasons = _identity_reasons(trusted, program_match, organizer_match)
    status = _identity_status(trusted, program_match, organizer_match)
    return SourceIdentityDecision(
        status,
        organizer_match,
        program_match,
        trusted,
        tuple(reasons),
    )


def _trusted_host(host: str, official_hosts: tuple[str, ...]) -> bool:
    normalized = tuple(item.lower().lstrip(".") for item in official_hosts)
    official = any(host == item or host.endswith(f".{item}") for item in normalized)
    return official or host.endswith((".gov.tw", ".edu.tw"))


def _identity_status(
    trusted: bool,
    program_match: bool,
    organizer_match: bool,
) -> str:
    if not program_match:
        return SOURCE_REJECTED
    if trusted and organizer_match:
        return SOURCE_VERIFIED
    if trusted:
        return SOURCE_REVIEW
    return SOURCE_REJECTED


def _identity_reasons(
    trusted: bool,
    program_match: bool,
    organizer_match: bool,
) -> list[str]:
    return [
        "方案名稱已命中" if program_match else "方案名稱未命中",
        "主辦單位已命中" if organizer_match else "主辦單位未命中",
        "來源網域可信" if trusted else "來源網域尚未信任",
    ]


def _compact(value: str) -> str:
    return "".join(value.lower().split())
