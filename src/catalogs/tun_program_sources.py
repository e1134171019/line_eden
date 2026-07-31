# -*- coding: utf-8 -*-

from dataclasses import replace

from src.catalogs.tun_2025_program_catalog import (
    OFFICIAL_VERIFIED,
    TUN_2025_PROGRAMS,
    ScholarshipProgramWatch,
)

SOURCE_RELAY = "institutional_relay"
SOURCE_CORE = "covered_by_core_source"
SOURCE_PENDING = "pending"


# 直接官方入口失效時，以主辦單位新頁面取代；沒有公開官網者使用政府／學校正式轉載。
_SOURCE_OVERRIDES: dict[str, tuple[str, str]] = {
    "it-social-care": (
        "https://www.csroc.org.tw/page.jsp?ID=41",
        OFFICIAL_VERIFIED,
    ),
    "sunshine-scholarship": (
        "https://scholarship.sunshine.org.tw/?cat=1",
        OFFICIAL_VERIFIED,
    ),
    "sunshine-wanzu": (
        "https://scholarship.sunshine.org.tw/?cat=1",
        OFFICIAL_VERIFIED,
    ),
    "auden-innovation-research": (
        "https://www.auden.com.tw/news-4/",
        OFFICIAL_VERIFIED,
    ),
    "auden-university-talent": (
        "https://www.auden.com.tw/news-4/",
        OFFICIAL_VERIFIED,
    ),
    "heart-child": (
        "https://www.ccft.org.tw/OnePage.aspx?tid=148",
        OFFICIAL_VERIFIED,
    ),
    "harmony-stability": (
        "https://rsd.fashui.org/archives/33101",
        OFFICIAL_VERIFIED,
    ),
    "tcb-foundation": (
        "https://student.nutc.edu.tw/p/406-1020-117849%2Cr34.php?Lang=zh-tw",
        SOURCE_RELAY,
    ),
    "tainan-kaiji": (
        "https://service.utaipei.edu.tw/p/404-1034-131943.php?Lang=zh-tw",
        SOURCE_RELAY,
    ),
    "rehe-association": (
        "https://service.utaipei.edu.tw/p/404-1034-125939.php?Lang=zh-tw",
        SOURCE_RELAY,
    ),
    "chiu-filial-piety": (
        "https://pyjh.chc.edu.tw/posts/1238",
        SOURCE_RELAY,
    ),
    "dapeng-aid": (
        "https://www.hn.thu.edu.tw/web/school/announcement.php?aid=12909&cid=4&department=15",
        SOURCE_RELAY,
    ),
    # 兩項主辦單位官網在 GitHub Runner TLS／握手失敗；既有教育部圓夢助學網已監測。
    "yonglin-hope": ("", SOURCE_CORE),
    "hndasset-wenxiang": ("", SOURCE_CORE),
}


def resolved_programs() -> tuple[ScholarshipProgramWatch, ...]:
    """套用經真實 smoke 與官方資料核對後的來源設定。"""

    resolved: list[ScholarshipProgramWatch] = []
    for item in TUN_2025_PROGRAMS:
        override = _SOURCE_OVERRIDES.get(item.program_id)
        if override is None:
            resolved.append(item)
            continue
        url, status = override
        resolved.append(replace(item, official_url=url, official_status=status))
    return tuple(resolved)


def monitorable_programs() -> tuple[ScholarshipProgramWatch, ...]:
    """回傳本群組會直接下載的官方或正式機構轉載入口。"""

    return tuple(
        item
        for item in resolved_programs()
        if item.official_status in {OFFICIAL_VERIFIED, SOURCE_RELAY}
    )


def core_covered_programs() -> tuple[ScholarshipProgramWatch, ...]:
    """回傳已由六核心來源中的教育部圓夢助學網涵蓋的方案。"""

    return tuple(
        item for item in resolved_programs() if item.official_status == SOURCE_CORE
    )


def unresolved_programs() -> tuple[ScholarshipProgramWatch, ...]:
    """回傳仍沒有可靠官方或正式轉載來源的方案。"""

    return tuple(
        item for item in resolved_programs() if item.official_status == SOURCE_PENDING
    )


def validate_resolved_sources() -> None:
    """38 項都必須具有直接監測、核心來源覆蓋或明確待查狀態。"""

    programs = resolved_programs()
    if len(programs) != 38:
        raise ValueError("解析後方案數量必須為 38。")
    for item in programs:
        if item.official_status in {OFFICIAL_VERIFIED, SOURCE_RELAY}:
            if not item.official_url.startswith(("https://", "http://")):
                raise ValueError(f"可監測方案缺少網址：{item.program_id}")
        elif item.official_status == SOURCE_CORE:
            if item.official_url:
                raise ValueError(f"核心來源覆蓋方案不得重複請求：{item.program_id}")
        elif item.official_status == SOURCE_PENDING:
            if item.official_url:
                raise ValueError(f"待查方案不得偽造網址：{item.program_id}")
        else:
            raise ValueError(f"未知來源狀態：{item.program_id}")


validate_resolved_sources()
