# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from urllib.parse import urlparse


class ExtractionMode(StrEnum):
    """正文定位策略。"""

    STRICT_SELECTORS = "strict_selectors"
    PREFER_SELECTORS = "prefer_selectors"
    AUTO = "auto"


@dataclass(frozen=True)
class DetailExtractionPolicy:
    """單一網站或路徑的版本化正文擷取契約。"""

    name: str
    version: str
    mode: ExtractionMode
    include_selectors: tuple[str, ...]
    subtractive_selectors: tuple[str, ...]
    min_content_length: int = 20

    def config_hash(self) -> str:
        payload = json.dumps(
            {
                "name": self.name,
                "version": self.version,
                "mode": self.mode.value,
                "include": self.include_selectors,
                "subtract": self.subtractive_selectors,
                "minimum": self.min_content_length,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class AnnouncementContentExtraction:
    """正文文字與實際命中的政策／selector 診斷。"""

    text: str
    policy_name: str
    policy_version: str
    policy_hash: str
    selected_selector: str
    heuristic_fallback: bool


_COMMON_REMOVE = (
    "script",
    "style",
    "noscript",
    "header",
    "nav",
    "footer",
    "aside",
    "form",
    ".header",
    ".footer",
    ".navbar",
    ".menu",
    ".sidebar",
    ".breadcrumb",
    ".banner",
    ".slider",
    ".carousel",
    ".bx-wrapper",
    ".swiper",
    ".owl-carousel",
    ".module-banner",
    ".social-share",
    ".related-posts",
)

_DEFAULT_POLICY = DetailExtractionPolicy(
    "default-html",
    "1",
    ExtractionMode.AUTO,
    (
        "article",
        "main",
        "[role='main']",
        ".mpgdetail",
        ".mcont",
        ".module-detail",
        ".article-content",
        ".news-content",
        ".content-body",
        ".entry-content",
    ),
    _COMMON_REMOVE,
)
_LHU_POLICY = DetailExtractionPolicy(
    "lhu-html",
    "1",
    ExtractionMode.PREFER_SELECTORS,
    (
        ".mpgdetail",
        ".module-detail",
        ".mcont",
        ".module-detail-inner",
        "article",
        "main",
    ),
    _COMMON_REMOVE,
)
_AUDEN_POLICY = DetailExtractionPolicy(
    "auden-html",
    "1",
    ExtractionMode.PREFER_SELECTORS,
    (
        ".entry-content",
        ".et_pb_post_content",
        ".post-content",
        "article",
        "main",
    ),
    _COMMON_REMOVE,
)
_CCF_POLICY = DetailExtractionPolicy(
    "ccft-html",
    "1",
    ExtractionMode.PREFER_SELECTORS,
    (
        ".content",
        ".main-content",
        ".article-content",
        "main",
        "article",
    ),
    _COMMON_REMOVE,
)
_YZU_POLICY = DetailExtractionPolicy(
    "yzu-announcement-html",
    "1",
    ExtractionMode.PREFER_SELECTORS,
    (
        ".item-page",
        ".com-content-article",
        ".com-content-article__body",
        "[itemprop='articleBody']",
        ".article-content",
        "article",
        "main",
        "body",
    ),
    _COMMON_REMOVE,
    80,
)
_HT_POLICY = DetailExtractionPolicy(
    "ht-policy-html",
    "1",
    ExtractionMode.PREFER_SELECTORS,
    (
        "#content",
        ".main-content",
        ".content",
        ".article-content",
        "article",
        "main",
        "body",
    ),
    _COMMON_REMOVE,
    80,
)


# 依 host 選擇版本化正文政策；未知網站使用通用 policy。
def policy_for_url(source_url: str) -> DetailExtractionPolicy:
    host = (urlparse(source_url).hostname or "").lower()
    if host.endswith("lhu.edu.tw"):
        return _LHU_POLICY
    if host.endswith("auden.com.tw"):
        return _AUDEN_POLICY
    if host.endswith("ccft.org.tw"):
        return _CCF_POLICY
    if host == "announce.yzu.edu.tw":
        return _YZU_POLICY
    if host.endswith("ht.org.tw"):
        return _HT_POLICY
    return _DEFAULT_POLICY
