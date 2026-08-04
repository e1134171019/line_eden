# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re
from urllib.parse import urlparse

from src.discovery.search_provider import SearchHit

SOURCE_OFFICIAL = "official"
SOURCE_GOVERNMENT = "government_relay"
SOURCE_SCHOOL = "school_relay"
SOURCE_OTHER = "other"

_RULE_MARKERS = ("簡章", "辦法", "申請資格", "資格", "申請須知")
_APPLICATION_MARKERS = ("login", "signin", "apply", "報名系統", "登入")
_YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2}|1\d{2})(?!\d)")


@dataclass(frozen=True)
class RankedSourceCandidate:
    """保留候選來源分數、角色與可稽核理由。"""

    hit: SearchHit
    score: int
    source_role: str
    reasons: tuple[str, ...]
    verification_status: str = "candidate"


# 依官方網域、正式轉載、方案名稱、主辦單位與年度訊號排序。
def rank_source_candidates(
    hits: list[SearchHit],
    title: str,
    organizer: str,
    aliases: tuple[str, ...] = tuple(),
    official_hosts: tuple[str, ...] = tuple(),
    *,
    current_year: int,
) -> tuple[RankedSourceCandidate, ...]:
    candidates = [
        _rank_hit(hit, title, organizer, aliases, official_hosts, current_year)
        for hit in hits
    ]
    return tuple(sorted(candidates, key=lambda item: (-item.score, item.hit.url)))


def _rank_hit(
    hit: SearchHit,
    title: str,
    organizer: str,
    aliases: tuple[str, ...],
    official_hosts: tuple[str, ...],
    current_year: int,
) -> RankedSourceCandidate:
    text = _normalized_text(hit)
    host = (urlparse(hit.url).hostname or "").lower()
    role, score, reasons = _source_role(host, official_hosts)
    score += _name_score(text, title, aliases, reasons)
    score += _organizer_score(text, organizer, reasons)
    score += _year_score(text, current_year, reasons)
    score += _document_score(text, hit.url, reasons)
    return RankedSourceCandidate(hit, score, role, tuple(reasons))


def _source_role(
    host: str,
    official_hosts: tuple[str, ...],
) -> tuple[str, int, list[str]]:
    normalized_hosts = tuple(item.lower().lstrip(".") for item in official_hosts)
    if any(host == item or host.endswith(f".{item}") for item in normalized_hosts):
        return SOURCE_OFFICIAL, 100, ["官方主辦單位網域"]
    if host.endswith(".gov.tw"):
        return SOURCE_GOVERNMENT, 85, ["政府機關正式來源"]
    if host.endswith(".edu.tw"):
        return SOURCE_SCHOOL, 75, ["學校正式轉載"]
    return SOURCE_OTHER, 0, ["尚未驗證來源身分"]


def _name_score(
    text: str,
    title: str,
    aliases: tuple[str, ...],
    reasons: list[str],
) -> int:
    names = tuple(dict.fromkeys((title, *aliases)))
    matched = next((name for name in names if _compact(name) in text), "")
    if not matched:
        return 0
    reasons.append(f"方案名稱命中：{matched}")
    return 35


def _organizer_score(text: str, organizer: str, reasons: list[str]) -> int:
    if not organizer or _compact(organizer) not in text:
        return 0
    reasons.append("主辦單位名稱命中")
    return 30


def _year_score(text: str, current_year: int, reasons: list[str]) -> int:
    roc_year = current_year - 1911
    years = {int(value) for value in _YEAR_PATTERN.findall(text)}
    if current_year in years or roc_year in years:
        reasons.append("當年度訊號命中")
        return 25
    if years:
        reasons.append("僅命中其他年度")
        return -30
    return 0


def _document_score(text: str, url: str, reasons: list[str]) -> int:
    score = 0
    if any(marker in text for marker in _RULE_MARKERS):
        reasons.append("含辦法或資格訊號")
        score += 15
    normalized_url = url.lower()
    if normalized_url.endswith(".pdf"):
        reasons.append("直接 PDF 文件")
        score += 10
    if any(marker in normalized_url or marker in text for marker in _APPLICATION_MARKERS):
        reasons.append("疑似僅為申請登入入口")
        score -= 40
    return score


def _normalized_text(hit: SearchHit) -> str:
    return _compact(" ".join((hit.title, hit.snippet, hit.published_date)))


def _compact(value: str) -> str:
    return "".join(value.lower().split())
