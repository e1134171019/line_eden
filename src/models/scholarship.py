# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import datetime
import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# 正規化文字欄位，避免雜訊造成雜湊不穩定。
def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


# 將日期轉成 YYYY-MM-DD；格式異常時保留原值。
def _normalize_date(date_text: str) -> str:
    value = _normalize_text(date_text)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return value


# 正規化公告網址中的大小寫、query 順序與 fragment，保留具有語意的參數。
def normalize_source_url(source_url: str) -> str:
    normalized = _normalize_text(source_url)
    parsed = urlsplit(normalized)
    if not parsed.scheme or not parsed.netloc:
        return normalized
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return normalized
    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    host_text = f"[{hostname}]" if ":" in hostname else hostname
    netloc = host_text if port is None or default_port else f"{host_text}:{port}"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, parsed.path, query, ""))


# 由來源與公告網址建立跨標題、日期改動仍穩定的公告識別碼。
def build_announcement_id(source: str, source_url: str) -> str:
    payload = "|".join(
        [
            _normalize_text(source).casefold(),
            normalize_source_url(source_url),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# 由穩定欄位建立內容雜湊，供資料去重。
def build_content_hash(source: str, title: str, published_date: str, source_url: str) -> str:
    payload = "|".join([
        _normalize_text(source),
        _normalize_text(title),
        _normalize_date(published_date),
        _normalize_text(source_url),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# 依標題區分獎學金、助學金、貸款與其他補助。
def _classify_title(title: str) -> str:
    normalized = _normalize_text(title)
    if "就學貸款" in normalized:
        return "loan"
    if "獎助學金" in normalized or "獎學金" in normalized:
        return "scholarship"
    if "助學金" in normalized or "扶助學生" in normalized:
        return "student_aid"
    if any(marker in normalized for marker in ("補助", "減免", "津貼", "扶助")):
        return "subsidy"
    return "other"


@dataclass(frozen=True)
class Scholarship:
    source: str
    title: str
    published_date: str
    source_url: str
    category: str
    content_hash: str
    announcement_id: str = ""
    notice_kind: str = "unknown"
    eligibility_status: str = ""
    eligibility_reason: str = ""

    # 將原始欄位正規化並產生 Scholarship 物件。
    @classmethod
    def from_raw(
        cls,
        source: str,
        title: str,
        published_date: str,
        source_url: str,
    ) -> "Scholarship":
        normalized_source = _normalize_text(source)
        normalized_title = _normalize_text(title)
        normalized_date = _normalize_date(published_date)
        normalized_url = _normalize_text(source_url)
        return cls(
            source=normalized_source,
            title=normalized_title,
            published_date=normalized_date,
            source_url=normalized_url,
            category=_classify_title(normalized_title),
            content_hash=build_content_hash(
                source=normalized_source,
                title=normalized_title,
                published_date=normalized_date,
                source_url=normalized_url,
            ),
            announcement_id=build_announcement_id(
                source=normalized_source,
                source_url=normalized_url,
            ),
        )
