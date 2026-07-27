# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import datetime
import hashlib


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


# 由穩定欄位建立內容雜湊，供資料去重。
def build_content_hash(source: str, title: str, published_date: str, source_url: str) -> str:
    payload = "|".join([
        _normalize_text(source),
        _normalize_text(title),
        _normalize_date(published_date),
        _normalize_text(source_url),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        )
