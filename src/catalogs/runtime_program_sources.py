# -*- coding: utf-8 -*-

from dataclasses import replace
from urllib.parse import urlparse

from src.catalogs.tun_2025_program_catalog import OFFICIAL_VERIFIED
from src.catalogs.tun_program_sources import (
    SOURCE_RELAY,
    ResolvedProgramSource,
    resolved_programs,
)
from src.models.source_quality import SourceRisk, SourceUrlType, is_monitorable_url_type

# Production 實際抓取證明失效後，改用已人工核對且可長期追蹤的正式入口。
_RUNTIME_SOURCE_PATCHES: dict[
    str,
    tuple[str, str, SourceUrlType, SourceRisk, tuple[str, ...]],
] = {
    "songliang-aid": (
        "https://www.slceas.org.tw/index.php/scholarship/scholarship01",
        OFFICIAL_VERIFIED,
        SourceUrlType.EVERGREEN,
        SourceRisk.LOW,
        ("https://www.slceas.org.tw/index.php/scholarship",),
    ),
    "hsinrong-emergency-aid": (
        "https://skjh.chc.edu.tw/posts/969",
        SOURCE_RELAY,
        SourceUrlType.RELAY_DETAIL,
        SourceRisk.HIGH,
        (
            "https://osa.nfu.edu.tw/zh_tw/4/help",
            "https://nfuosa.nfu.edu.tw/life/help.html",
        ),
    ),
    "buddha-charity-progress": (
        "https://service.utaipei.edu.tw/p/404-1034-130714.php?Lang=zh-tw",
        SOURCE_RELAY,
        SourceUrlType.RELAY_DETAIL,
        SourceRisk.HIGH,
        (
            "https://www.buddha-charity.org/main.php?funName=news_content&id=114",
            "https://www.buddha-charity.org/",
        ),
    ),
    "yonglin-hope": (
        "https://service.utaipei.edu.tw/p/404-1034-133653.php?Lang=zh-tw",
        SOURCE_RELAY,
        SourceUrlType.RELAY_DETAIL,
        SourceRisk.HIGH,
        (
            "https://www.yonglin.org.tw/project/education/detail/28",
            "https://www.yonglin.org.tw/project/education",
        ),
    ),
    "sunshine-scholarship": (
        "https://scls.sunshine.org.tw/",
        OFFICIAL_VERIFIED,
        SourceUrlType.EVERGREEN,
        SourceRisk.LOW,
        (
            "https://www.sunshine.org.tw/news/announce",
            "https://scholarship.sunshine.org.tw/?cat=1",
        ),
    ),
    "sunshine-wanzu": (
        "https://www.sunshine.org.tw/news/announce",
        OFFICIAL_VERIFIED,
        SourceUrlType.LIST,
        SourceRisk.LOW,
        (
            "https://scholarship.sunshine.org.tw/?cat=1",
            "https://scholarship.sunshine.org.tw/?p=996",
        ),
    ),
    "lovepeace-disadvantaged": (
        "https://service.utaipei.edu.tw/p/404-1034-125916.php?Lang=zh-tw",
        SOURCE_RELAY,
        SourceUrlType.RELAY_DETAIL,
        SourceRisk.HIGH,
        (
            "https://www.lovepeace.org.tw/Download.php?CataP=7&N_Key=192",
            "https://www.lovepeace.org.tw/",
        ),
    ),
    "dapeng-aid": (
        "https://nfuosa.nfu.edu.tw/scholarship-news/181-life/sact-scholarship/scholarshipcc.html",
        SOURCE_RELAY,
        SourceUrlType.RELAY_LIST,
        SourceRisk.MEDIUM,
        (
            "https://nfuosa.nfu.edu.tw/%E6%9C%80%E6%96%B0%E6%B6%88%E6%81%AF/181-life/sact-scholarship/scholarshipcc/9722-115%E5%B9%B4%E7%AC%AC1%E6%AC%A1%E5%A4%A7%E9%B5%AC%E7%A7%91%E6%8A%80%E6%85%88%E5%96%84%E5%9F%BA%E9%87%91%E6%9C%83%E7%8D%8E%E5%8A%A9%E5%AD%B8%E9%87%91.html",
            "https://www.edu.tw/helpdreams/Grants_Content.aspx?n=2BBF7170197CE7D3&s=68651C4217F75095&sms=0A01A72AAB9E5CD4",
        ),
    ),
    "hndasset-wenxiang": (
        "https://assistance.ncnu.edu.tw/p/403-1079-249-1.php?Lang=zh-tw",
        SOURCE_RELAY,
        SourceUrlType.RELAY_LIST,
        SourceRisk.MEDIUM,
        (
            "https://www.hndasset.com/csr/",
            "https://assistance.ncnu.edu.tw/p/412-1079-694.php?Lang=zh-tw",
        ),
    ),
    "harmony-stability": (
        "https://rsd.fashui.org/archives/category/news",
        OFFICIAL_VERIFIED,
        SourceUrlType.LIST,
        SourceRisk.LOW,
        (
            "https://rsd.fashui.org/archives/33101",
            "https://www.hk.edu.tw/remote/HKlf_1238963/",
        ),
    ),
}

# 年度會改寫，但已由 live HTML 證明的穩定標題片段。
_RUNTIME_ALIASES: dict[str, tuple[str, ...]] = {
    "tf4dr-aid": (
        "學年度第1學期助學金",
        "學年度第2學期助學金",
    ),
    "hsinrong-emergency-aid": (
        "欣榮圖書館急難學生助學金",
        "竹山欣榮圖書館急難學生助學金",
    ),
    "lovepeace-disadvantaged": (
        "祥和文教基金會優秀清寒獎學金獎助學金",
        "優秀清寒獎學金獎助學金",
    ),
}


def _hosts(urls: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                host
                for url in urls
                if (host := urlparse(url).hostname)
            }
        )
    )


# 套用 production 失敗證據，不覆寫原始 provenance。
def _patch_source(item: ResolvedProgramSource) -> ResolvedProgramSource:
    aliases = tuple(dict.fromkeys((*item.aliases, *_RUNTIME_ALIASES.get(item.program_id, ()))))
    patch = _RUNTIME_SOURCE_PATCHES.get(item.program_id)
    if patch is None:
        return replace(item, aliases=aliases)
    url, status, url_type, risk, fallbacks = patch
    merged_fallbacks = tuple(
        dict.fromkeys((*fallbacks, item.official_url, *item.fallback_urls))
    )
    return replace(
        item,
        aliases=aliases,
        official_url=url,
        official_status=status,
        source_url_type=url_type,
        update_risk=risk,
        fallback_urls=merged_fallbacks,
        allowed_hosts=_hosts((url, *merged_fallbacks)),
        expected_discovery=(
            f"{item.title}：production 主入口失敗時依序使用正式 fallback；"
            "實際使用入口必須寫入來源狀態。"
        ),
        last_verified_at="2026-08-02",
    )


# 回傳正式執行使用的 38 項來源。
def runtime_resolved_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(_patch_source(item) for item in resolved_programs())


# 回傳正式執行可直接抓取的來源。
def runtime_monitorable_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(
        item
        for item in runtime_resolved_programs()
        if item.official_status in {OFFICIAL_VERIFIED, SOURCE_RELAY}
        and is_monitorable_url_type(item.source_url_type)
    )
