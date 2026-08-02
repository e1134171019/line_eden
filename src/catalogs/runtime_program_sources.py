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
        "https://scls.sunshine.org.tw/",
        OFFICIAL_VERIFIED,
        SourceUrlType.EVERGREEN,
        SourceRisk.MEDIUM,
        (
            "https://www.sunshine.org.tw/news/announce",
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
        "https://osa.ndhu.edu.tw/p/406-1005-254221%2Cr402.php?Lang=zh-tw",
        SOURCE_RELAY,
        SourceUrlType.RELAY_DETAIL,
        SourceRisk.HIGH,
        (
            "https://www.ntin.edu.tw/news_detail.aspx?id=50777",
            "https://www.osa.nchu.edu.tw/osa/laa/sys/modules/tadnews/index.php?nsn=4145",
            "https://studentaff.ctu.edu.tw/p/404-1003-47891.php?Lang=zh-tw",
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
    "dapeng-aid": (
        "大鵬科技慈善基金會115年第一次獎助學金",
        "大鵬科技慈善基金會115年第1次獎助學金",
        "大鵬獎助學金",
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
