# -*- coding: utf-8 -*-

from dataclasses import dataclass, replace
from urllib.parse import urlparse

from src.catalogs.tun_program_sources import (
    ResolvedProgramSource,
    monitorable_programs,
    resolved_programs,
)
from src.models.source_quality import SourceUrlType


@dataclass(frozen=True)
class LiveSourceOverride:
    """正式執行使用的健康入口、URL 類型與優先 fallback。"""

    primary_url: str = ""
    source_url_type: SourceUrlType | None = None
    fallback_urls: tuple[str, ...] = tuple()


_LIVE_SOURCE_OVERRIDES: dict[str, LiveSourceOverride] = {
    "buddha-charity-progress": LiveSourceOverride(
        primary_url=(
            "https://service.utaipei.edu.tw/p/404-1034-130714.php?Lang=zh-tw"
        ),
        source_url_type=SourceUrlType.RELAY_DETAIL,
        fallback_urls=(
            "https://www.buddha-charity.org/main.php?funName=news_content&id=114",
            "https://www.buddha-charity.org/main.php?funName=news_content&id=109",
            "https://www.buddha-charity.org/",
        ),
    ),
    "yonglin-hope": LiveSourceOverride(
        primary_url=(
            "https://service.utaipei.edu.tw/p/404-1034-133653.php?Lang=zh-tw"
        ),
        source_url_type=SourceUrlType.RELAY_DETAIL,
        fallback_urls=(
            "https://www.yonglin.org.tw/project/education/detail/28",
            "https://www.yonglin.org.tw/project/education",
        ),
    ),
    "sunshine-scholarship": LiveSourceOverride(
        primary_url="https://scls.sunshine.org.tw/",
        source_url_type=SourceUrlType.EVERGREEN,
        fallback_urls=(
            "https://www.sunshine.org.tw/news/announce",
            "https://scholarship.sunshine.org.tw/",
        ),
    ),
    "sunshine-wanzu": LiveSourceOverride(
        primary_url=(
            "https://announce.yzu.edu.tw/index.php/tw/st/"
            "st-lgs20250828-1100-01"
        ),
        source_url_type=SourceUrlType.RELAY_DETAIL,
        fallback_urls=(
            "https://www.sunshine.org.tw/news/announce",
            "https://scholarship.sunshine.org.tw/?cat=1",
        ),
    ),
    "dapeng-aid": LiveSourceOverride(
        primary_url=(
            "https://osa.ndhu.edu.tw/p/406-1005-254221%2Cr402.php?Lang=zh-tw"
        ),
        source_url_type=SourceUrlType.RELAY_DETAIL,
        fallback_urls=(
            "https://osa.ndhu.edu.tw/p/403-1005-402.php?Lang=zh-tw",
        ),
    ),
}

_LIVE_ALIASES: dict[str, tuple[str, ...]] = {
    "tf4dr-aid": (
        "學年度第1學期助學金",
        "學年度第2學期助學金",
    ),
    "hsinrong-emergency-aid": (
        "竹山欣榮圖書館急難學生助學金",
        "欣榮圖書館急難學生助學金",
    ),
    "lovepeace-disadvantaged": (
        "祥和文教基金會獎助學金",
        "祥和文教基金會獎助學金申請辦法",
    ),
    "sunshine-scholarship": (
        "獎助學金申請說明",
        "陽光獎助學金申請說明",
    ),
}


# 保留人工契約，僅在正式抓取時加入已驗證入口與實際網站標題。
def apply_live_source_override(
    program: ResolvedProgramSource,
) -> ResolvedProgramSource:
    override = _LIVE_SOURCE_OVERRIDES.get(program.program_id, LiveSourceOverride())
    primary_url = override.primary_url or program.official_url
    source_url_type = override.source_url_type or program.source_url_type
    fallback_urls = _unique_urls(
        (*override.fallback_urls, *program.fallback_urls),
        primary_url,
    )
    aliases = tuple(
        dict.fromkeys((*program.aliases, *_LIVE_ALIASES.get(program.program_id, tuple())))
    )
    return replace(
        program,
        aliases=aliases,
        official_url=primary_url,
        source_url_type=source_url_type,
        fallback_urls=fallback_urls,
        allowed_hosts=_allowed_hosts(primary_url, fallback_urls),
    )


# 正式 collector 使用已套用 live 覆寫的可監測方案。
def live_monitorable_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(apply_live_source_override(item) for item in monitorable_programs())


# 逐項狀態輸出仍依完整 38 項目錄順序排列。
def live_resolved_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(apply_live_source_override(item) for item in resolved_programs())


# 回傳不重複且不等於主入口的 fallback。
def _unique_urls(urls: tuple[str, ...], primary_url: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(url for url in urls if url and url != primary_url))


# 主入口與 fallback host 都必須列入合法範圍。
def _allowed_hosts(primary_url: str, fallback_urls: tuple[str, ...]) -> tuple[str, ...]:
    hosts = {
        host
        for url in (primary_url, *fallback_urls)
        if (host := urlparse(url).hostname)
    }
    return tuple(sorted(hosts))
