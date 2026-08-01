# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from urllib.parse import urlsplit


class ExtractionMode(str, Enum):
    """來源 selector 與通用 heuristic 的協作方式。"""

    AUTO = "auto"
    PREFER_SELECTORS = "prefer_selectors"
    STRICT_SELECTORS = "strict_selectors"


@dataclass(frozen=True)
class DetailExtractionPolicy:
    """單一來源可版本化的正文擷取規則。"""

    name: str
    version: str
    mode: ExtractionMode
    include_selectors: tuple[str, ...]
    subtractive_selectors: tuple[str, ...]
    min_content_length: int


@dataclass(frozen=True)
class SourceExtractionPolicyRule:
    """以 hostname suffix 對應來源抽取規則。"""

    hostname_suffix: str
    policy: DetailExtractionPolicy


@dataclass(frozen=True)
class ExtractedAnnouncementContent:
    """正文與本次實際使用的抽取 metadata。"""

    text: str
    selector_used: str
    used_fallback: bool
    policy_name: str
    policy_hash: str


def resolve_detail_extraction_policy(
    source_url: str,
    rules: tuple[SourceExtractionPolicyRule, ...],
    default_policy: DetailExtractionPolicy,
) -> DetailExtractionPolicy:
    """依最長 hostname suffix 選出有效抽取規則。"""
    hostname = (urlsplit(source_url).hostname or "").lower()
    matches = [
        rule
        for rule in rules
        if hostname == rule.hostname_suffix
        or hostname.endswith(f".{rule.hostname_suffix}")
    ]
    if not matches:
        return default_policy
    return max(matches, key=lambda rule: len(rule.hostname_suffix)).policy


def build_extraction_policy_hash(policy: DetailExtractionPolicy) -> str:
    """將 effective extraction config 轉成可比較的 deterministic hash。"""
    payload = {
        "name": policy.name,
        "version": policy.version,
        "mode": policy.mode.value,
        "include_selectors": policy.include_selectors,
        "subtractive_selectors": policy.subtractive_selectors,
        "min_content_length": policy.min_content_length,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_named_extraction_hash(
    name: str,
    version: str,
    settings: tuple[str, ...] = tuple(),
) -> str:
    """替非 HTML parser 建立同格式的 effective config hash。"""
    payload = "|".join((name.strip(), version.strip(), *settings))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
