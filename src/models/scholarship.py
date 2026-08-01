# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import datetime
import hashlib


# 正規化文字欄位，避免雜訊造成雜湊不穩定。
def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


# 將日期轉成 YYYY-MM-DD；格式異常或未知時保留原值。
def _normalize_date(date_text: str) -> str:
    value = _normalize_text(date_text)
    if not value:
        return ""
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


# 依標題區分獎學金、助學金、貸款與其他補助。
def _classify_title(title: str) -> str:
    normalized = _normalize_text(title)
    if "就學貸款" in normalized:
        return "loan"
    if any(marker in normalized for marker in ("獎助學金", "獎學金", "獎助金", "獎勵學金")):
        return "scholarship"
    if any(marker in normalized for marker in ("助學金", "助學計畫", "扶助學生", "濟助")):
        return "student_aid"
    if any(marker in normalized for marker in ("補助", "減免", "津貼", "扶助")):
        return "subsidy"
    return "other"


# TUN 已知方案可由既有 source id 推導 program id，兼容舊 collector。
def _infer_program_id(source: str, program_id: str) -> str:
    normalized = _normalize_text(program_id)
    if normalized:
        return normalized
    prefix = "tun-program-"
    return source[len(prefix):] if source.startswith(prefix) else ""


@dataclass(frozen=True)
class Scholarship:
    source: str
    title: str
    published_date: str
    source_url: str
    category: str
    content_hash: str
    program_id: str = ""
    entry_url: str = ""
    detail_url: str = ""
    notice_kind: str = "unknown"
    application_status: str = "not_applicable"
    eligibility_status: str = ""
    eligibility_reason: str = ""
    manual_checks: tuple[str, ...] = tuple()
    review_kind: str = ""
    exclusion_reason: str = ""

    # 將原始欄位正規化並產生 Scholarship 物件。
    @classmethod
    def from_raw(
        cls,
        source: str,
        title: str,
        published_date: str,
        source_url: str,
        *,
        program_id: str = "",
        entry_url: str = "",
        detail_url: str = "",
    ) -> "Scholarship":
        normalized_source = _normalize_text(source)
        normalized_title = _normalize_text(title)
        normalized_date = _normalize_date(published_date)
        normalized_url = _normalize_text(source_url)
        normalized_entry = _normalize_text(entry_url) or normalized_url
        normalized_detail = _normalize_text(detail_url) or normalized_url
        resolved_program_id = _infer_program_id(normalized_source, program_id)
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
            program_id=resolved_program_id,
            entry_url=normalized_entry,
            detail_url=normalized_detail,
        )
