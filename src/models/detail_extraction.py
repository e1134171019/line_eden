# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import StrEnum
import hashlib
from urllib.parse import urlparse


class ExtractionMode(StrEnum):
    AUTO = "auto"
    PREFER_SELECTORS = "prefer_selectors"
    STRICT_SELECTORS = "strict_selectors"


@dataclass(frozen=True)
class DetailExtractionPolicy:
    """單一網站的版本化正文抽取契約。"""

    name: str
    version: str
    mode: ExtractionMode
    include_selectors: tuple[str, ...]
    subtractive_selectors: tuple[str, ...]
    min_content_length: int = 20

    def config_hash(self) -> str:
        payload = "|".join(
            (
                self.name,
                self.version,
                self.mode.value,
                *self.include_selectors,
                "--subtract--",
                *self.subtractive_selectors,
                f"min={self.min_content_length}",
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SourceExtractionPolicyRule:
    host_suffix: str
    policy: DetailExtractionPolicy


@dataclass(frozen=True)
class AnnouncementContentExtraction:
    """正文文字與實際選擇器、fallback、政策雜湊。"""

    text: str
    policy_name: str
    policy_version: str
    policy_hash: str
    selected_selector: str
    heuristic_fallback: bool


_DEFAULT_REMOVE = (
    "script, style, noscript, header, nav, footer, aside, form, "
    ".header, .footer, .navbar, .menu, .sidebar, .breadcrumb, "
    ".banner, .slider, .carousel, .bx-wrapper, .swiper, .owl-carousel, "
    ".module-banner",
)
_DEFAULT_INCLUDE = (
    "article",
    "main",
    "[role='main']",
    ".mpgdetail",
    ".mcont",
    ".module-detail",
    ".article-content",
    ".news-content",
    ".content-body",
)

DEFAULT_POLICY = DetailExtractionPolicy(
    "default-html",
    "v2",
    ExtractionMode.AUTO,
    _DEFAULT_INCLUDE,
    _DEFAULT_REMOVE,
)
LHU_POLICY = DetailExtractionPolicy(
    "lhu-html",
    "v2",
    ExtractionMode.PREFER_SELECTORS,
    (".mpgdetail", ".module-detail", ".mcont"),
    _DEFAULT_REMOVE,
)
AUDEN_POLICY = DetailExtractionPolicy(
    "auden-html",
    "v1",
    ExtractionMode.PREFER_SELECTORS,
    (
        ".entry-content",
        ".post-content",
        ".elementor-widget-theme-post-content",
        "article",
        "main",
    ),
    _DEFAULT_REMOVE,
)

POLICY_RULES = (
    SourceExtractionPolicyRule("lhu.edu.tw", LHU_POLICY),
    SourceExtractionPolicyRule("auden.com.tw", AUDEN_POLICY),
)


def policy_for_url(url: str) -> DetailExtractionPolicy:
    """以 hostname suffix 選出目前生效的正文抽取政策。"""

    host = (urlparse(url).hostname or "").lower()
    for rule in POLICY_RULES:
        if host == rule.host_suffix or host.endswith(f".{rule.host_suffix}"):
            return rule.policy
    return DEFAULT_POLICY
