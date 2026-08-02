# -*- coding: utf-8 -*-

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult
from src.models.scholarship import Scholarship

_IGNORED_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}
_VOLATILE_TEXT = (
    re.compile(r"瀏覽(?:人次|次數)?\s*[:：]?\s*\d+"),
    re.compile(r"最後更新\s*[:：]?\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"),
)


# 移除追蹤參數、fragment 與多餘斜線，保留真正識別公告的 URL。
def canonicalize_announcement_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.casefold() not in _IGNORED_QUERY_KEYS
        )
    )
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            path.rstrip("/") or "/",
            query,
            "",
        )
    )


# 方案 ID 優先；一般公告以來源與正規化正文 URL 建立穩定識別。
def build_announcement_id(item: Scholarship) -> str:
    identity = item.program_id or canonicalize_announcement_url(
        item.detail_url or item.source_url
    )
    payload = f"{item.source}|{identity}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# 正文、主要辦法附件與解析政策實質改變時才產生新 revision。
def build_revision_hash(item: Scholarship, result: DetailFetchResult) -> str:
    rules = sorted(
        _stable_text(attachment.text)
        for attachment in result.extracted_attachments
        if attachment.status == "success"
        and attachment.content_role == "scholarship_rules"
        and attachment.text.strip()
    )
    source = result.source
    payload = "\n---\n".join(
        [
            build_announcement_id(item),
            canonicalize_announcement_url(source.final_url or source.requested_url),
            _stable_text(result.body_text or result.text),
            *rules,
            result.rules_status,
            source.extraction_policy_hash,
            source.selected_selector,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# 壓縮空白並移除不應觸發重新通知的瀏覽量與頁尾更新文字。
def _stable_text(text: str) -> str:
    normalized = " ".join(text.split())
    for pattern in _VOLATILE_TEXT:
        normalized = pattern.sub("", normalized)
    return " ".join(normalized.split())
