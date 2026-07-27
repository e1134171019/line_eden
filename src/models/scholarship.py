# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import datetime
import hashlib
import re
import unicodedata


# 正規化文字欄位，避免雜訊造成雜湊不穩定。
def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


# 將日期轉成 YYYY-MM-DD；格式異常時保留原值。
def _normalize_date(date_text: str) -> str:
    value = _normalize_text(date_text)
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    return value


# 由穩定欄位建立單一來源內容雜湊，維持既有 SQLite 相容性。
def build_content_hash(source: str, title: str, published_date: str, source_url: str) -> str:
    payload = "|".join([
        _normalize_text(source),
        _normalize_text(title),
        _normalize_date(published_date),
        _normalize_text(source_url),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# 移除轉知、公告與版面符號，保留年度及獎學金名稱供跨來源去重。
def normalize_dedup_title(title: str) -> str:
    value = unicodedata.normalize("NFKC", _normalize_text(title)).lower()
    value = re.sub(r"[【〖\[（(][^】〗\]）)]{0,20}[】〗\]）)]", "", value)
    value = re.sub(r"^(轉知|公告|重要資訊|最新消息|訊息公告|有關|檢送|函轉)+[：:－\-｜|]*", "", value)
    value = re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE)
    return value


# 建立跨來源去重雜湊；不同來源的同名同年度公告會共用此值。
def build_dedup_hash(title: str) -> str:
    normalized = normalize_dedup_title(title)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# 依標題關鍵字判斷公告類型。
def _classify_title(title: str) -> str:
    normalized = _normalize_text(title)
    if "就學貸款" in normalized:
        return "loan"
    if "補助" in normalized or "減免" in normalized or "扶助" in normalized:
        return "subsidy"
    if "獎學金" in normalized or "助學金" in normalized:
        return "scholarship"
    return "other"


@dataclass(frozen=True)
class Scholarship:
    source: str
    title: str
    published_date: str
    source_url: str
    category: str
    content_hash: str
    notice_kind: str = "unknown"
    eligibility_status: str = ""
    eligibility_reason: str = ""
    dedup_hash: str = ""

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
            dedup_hash=build_dedup_hash(normalized_title),
        )
