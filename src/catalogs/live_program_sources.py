# -*- coding: utf-8 -*-

from dataclasses import dataclass, replace
from urllib.parse import urlparse

from src.catalogs.tun_program_sources import (
    SOURCE_RELAY,
    ResolvedProgramSource,
    resolved_programs,
)
from src.models.source_quality import SourceRisk, SourceUrlType, is_monitorable_url_type

_SUNSHINE_ANNOUNCEMENT_URL = "https://www.sunshine.org.tw/news/announce/0/10"
_SUNSHINE_APPLICATION_URL = "https://scls.sunshine.org.tw/"
_SUNSHINE_RELAY_URL = (
    "https://announce.yzu.edu.tw/index.php/tw/st/st-lgs20250828-1100-01"
)
_SUNSHINE_ANNOUNCEMENT_FALLBACK = "https://www.sunshine.org.tw/news/announce/0/20"


@dataclass(frozen=True)
class LiveSourceOverride:
    """由 production 稽核確認的可執行來源覆寫。"""

    primary_url: str
    official_status: str
    source_url_type: SourceUrlType
    fallback_urls: tuple[str, ...] = tuple()
    aliases: tuple[str, ...] = tuple()
    update_risk: SourceRisk = SourceRisk.MEDIUM
    inherit_existing_fallbacks: bool = True


# 只放 production 已證實失敗或 matcher 漏抓的來源。
_LIVE_OVERRIDES: dict[str, LiveSourceOverride] = {
    "tf4dr-aid": LiveSourceOverride(
        "https://www.tf4dr.org/posts",
        "verified",
        SourceUrlType.LIST,
        ("https://www.tf4dr.org/posts/240",),
        ("學年度第1學期助學金", "學年度第2學期助學金"),
        SourceRisk.LOW,
    ),
    "hsinrong-emergency-aid": LiveSourceOverride(
        "https://osa.nfu.edu.tw/zh_tw/4/help",
        SOURCE_RELAY,
        SourceUrlType.RELAY_LIST,
        (
            "https://skjh.chc.edu.tw/posts/969",
            "https://www.hsinrong.org/",
        ),
        ("欣榮圖書館急難學生助學金", "欣榮急難學生助學金"),
    ),
    "lijin-taoyuan": LiveSourceOverride(
        "https://www.lijin.com.tw/Extend/Foundation/News",
        "verified",
        SourceUrlType.LIST,
        ("https://www.lijin.com.tw/Extend/Foundation/Application",),
        ("清寒獎助學金", "年度清寒獎助學金開放申請"),
        SourceRisk.LOW,
    ),
    "buddha-charity-progress": LiveSourceOverride(
        "https://www.cksh.tp.edu.tw/news/%E3%80%901142%E7%8D%8E%E5%8A%A9%E5%AD%B8%E9%87%91%E3%80%91%E8%AA%8C%E5%96%84%E6%B8%85%E5%AF%92%E5%AD%B8%E7%94%9F%E9%80%B2%E6%AD%A5%E7%8D%8E%E5%AD%B8%E9%87%91/",
        SOURCE_RELAY,
        SourceUrlType.RELAY_DETAIL,
        ("https://www.buddha-charity.org/",),
        update_risk=SourceRisk.HIGH,
    ),
    "yonglin-hope": LiveSourceOverride(
        "https://activity-osa.ntunhs.edu.tw/p/412-1043-3282.php?Lang=zh-tw",
        SOURCE_RELAY,
        SourceUrlType.RELAY_LIST,
        (
            "https://service.utaipei.edu.tw/p/404-1034-133653.php?Lang=zh-tw",
            "https://activity-osa.ntunhs.edu.tw/p/406-1043-78366%2Cr2172.php?Lang=zh-tw",
            "https://www.yonglin.org.tw/project/education/detail/28",
        ),
    ),
    "sunshine-scholarship": LiveSourceOverride(
        _SUNSHINE_ANNOUNCEMENT_URL,
        "verified",
        SourceUrlType.LIST,
        (
            _SUNSHINE_APPLICATION_URL,
            _SUNSHINE_RELAY_URL,
            _SUNSHINE_ANNOUNCEMENT_FALLBACK,
        ),
        ("陽光獎助學金",),
        SourceRisk.LOW,
        False,
    ),
    "sunshine-wanzu": LiveSourceOverride(
        _SUNSHINE_ANNOUNCEMENT_URL,
        "verified",
        SourceUrlType.LIST,
        (
            _SUNSHINE_APPLICATION_URL,
            _SUNSHINE_RELAY_URL,
            _SUNSHINE_ANNOUNCEMENT_FALLBACK,
        ),
        ("萬足獎助學金", "萬足燒傷勞工子女獎助學金"),
        SourceRisk.LOW,
        False,
    ),
    "lovepeace-disadvantaged": LiveSourceOverride(
        "https://service.utaipei.edu.tw/p/404-1034-125916.php?Lang=zh-tw",
        SOURCE_RELAY,
        SourceUrlType.RELAY_DETAIL,
        (
            "https://www.lovepeace.org.tw/Download.php?CataP=7&N_Key=192",
            "https://www.lovepeace.org.tw/Policy.php?CataP=4&N_Key=189",
            "https://www.lovepeace.org.tw/",
        ),
        ("優秀清寒獎學金獎助學金",),
        SourceRisk.HIGH,
    ),
    "dapeng-aid": LiveSourceOverride(
        "https://osa.ndhu.edu.tw/p/406-1005-254221%2Cr402.php?Lang=zh-tw",
        SOURCE_RELAY,
        SourceUrlType.RELAY_DETAIL,
        (
            "https://www.tnssh.tn.edu.tw/2026/03/03/%E5%A4%A7%E9%B5%AC%E7%A7%91%E6%8A%80%E6%85%88%E5%96%84%E5%9F%BA%E9%87%91%E6%9C%83%E6%9C%83%E3%80%8C115%E5%B9%B4%E7%AC%AC1%E6%AC%A1%E7%8D%8E%E5%8A%A9%E5%AD%B8%E9%87%91%E3%80%8D%E3%80%90%E6%A0%A1/",
            "https://www.edu.tw/helpdreams/Grants_Content.aspx?n=2BBF7170197CE7D3&s=68651C4217F75095&sms=0A01A72AAB9E5CD4",
        ),
        update_risk=SourceRisk.HIGH,
    ),
}


# 將主入口與 fallback 的 host 一併列入合法來源範圍。
def _allowed_hosts(primary_url: str, fallbacks: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                host
                for url in (primary_url, *fallbacks)
                if (host := urlparse(url).hostname)
            }
        )
    )


# 套用 production 驗證後的入口、別名與 fallback。
def _apply_override(item: ResolvedProgramSource) -> ResolvedProgramSource:
    override = _LIVE_OVERRIDES.get(item.program_id)
    if override is None:
        return item
    inherited = item.fallback_urls if override.inherit_existing_fallbacks else tuple()
    fallbacks = tuple(
        dict.fromkeys(
            url
            for url in (*override.fallback_urls, *inherited)
            if url and url != override.primary_url
        )
    )
    aliases = tuple(dict.fromkeys((*item.aliases, *override.aliases)))
    return replace(
        item,
        aliases=aliases,
        official_url=override.primary_url,
        official_status=override.official_status,
        source_url_type=override.source_url_type,
        allowed_hosts=_allowed_hosts(override.primary_url, fallbacks),
        expected_discovery=(
            f"{item.title}：先使用 production 已驗證入口；失敗或無候選時依序使用 fallback。"
        ),
        update_risk=override.update_risk,
        fallback_urls=fallbacks,
    )


# 回傳真正供 production collector 使用的 38 項來源。
def live_resolved_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(_apply_override(item) for item in resolved_programs())


# 回傳 production 可直接下載的來源。
def live_monitorable_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(
        item
        for item in live_resolved_programs()
        if item.official_status in {"verified", SOURCE_RELAY}
        and is_monitorable_url_type(item.source_url_type)
    )
