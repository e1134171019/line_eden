# -*- coding: utf-8 -*-

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult

_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def build_announcement_id(source: str, detail_url: str) -> str:
    """以來源與正規化正文 URL 建立穩定公告識別。"""

    payload = f"{_normalize_text(source)}|{normalize_announcement_url(detail_url)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_announcement_url(url: str) -> str:
    """移除 fragment、追蹤參數並固定 query 排序。"""

    raw = " ".join(url.split()).strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS
        and not any(key.lower().startswith(prefix) for prefix in _TRACKING_QUERY_PREFIXES)
    ]
    normalized_path = re.sub(r"/{2,}", "/", parts.path or "/")
    if normalized_path != "/":
        normalized_path = normalized_path.rstrip("/")
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            normalized_path,
            urlencode(sorted(query)),
            "",
        )
    )


def build_revision_hash(fetch_result: DetailFetchResult) -> str:
    """只以正文、附件實質文字與辦法狀態建立 revision。"""

    body = _normalize_text(fetch_result.body_text or fetch_result.text)
    attachments = sorted(
        _normalize_text(item.text)
        for item in fetch_result.extracted_attachments
        if item.status == "success" and item.text.strip()
    )
    payload = "\n--BODY--\n" + body
    payload += "\n--ATTACHMENTS--\n" + "\n--NEXT--\n".join(attachments)
    payload += f"\n--RULES--\n{fetch_result.rules_status}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()
