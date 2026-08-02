# -*- coding: utf-8 -*-

from dataclasses import dataclass
from urllib.parse import urlparse

from src.catalogs.tun_2025_program_catalog import (
    OFFICIAL_VERIFIED,
    TUN_2025_PROGRAMS,
    ScholarshipProgramWatch,
)
from src.models.source_quality import (
    BLOCKED_URL_TYPES,
    SourceRisk,
    SourceUrlType,
    is_monitorable_url_type,
)

SOURCE_RELAY = "institutional_relay"
SOURCE_CORE = "covered_by_core_source"
SOURCE_PENDING = "pending"
VERIFIED_AT = "2026-08-02"


@dataclass(frozen=True)
class ResolvedProgramSource(ScholarshipProgramWatch):
    """保留原方案欄位，追加可供 collector 執行的來源品質契約。"""

    organizer_id: str = ""
    source_url_type: SourceUrlType = SourceUrlType.PENDING
    allowed_hosts: tuple[str, ...] = tuple()
    expected_discovery: str = ""
    update_risk: SourceRisk = SourceRisk.HIGH
    fallback_urls: tuple[str, ...] = tuple()
    last_verified_at: str = ""


_ORGANIZER_IDS = {
    "tf4dr-aid": "tf4dr-foundation",
    "foxconn-scholarship-whale": "foxconn-education-foundation",
    "avc-talented-student": "avc-education-foundation",
    "cfh-graduate": "cfh-foundation",
    "cfh-university": "cfh-foundation",
    "kumota-flying": "kumota-foundation",
    "lijin-taoyuan": "lijin-foundation",
    "tcb-foundation": "tcb-foundation",
    "tainan-kaiji": "tainan-kaiji",
    "songliang-aid": "slceas",
    "wang-yun-wu-self-study": "wang-yun-wu-foundation",
    "rehe-association": "rehe-association",
    "wisdomshare-service-learning": "wisdomshare-foundation",
    "hsinrong-emergency-aid": "hsinrong-foundation",
    "it-social-care": "csroc",
    "you-care-hand-in-hand": "puren-foundation",
    "chiu-filial-piety": "chiu-foundation",
    "buddha-charity-progress": "buddha-charity-foundation",
    "yonglin-hope": "yonglin-foundation",
    "cdf-vocational": "cdf-foundation",
    "ht-emergency": "ht-foundation",
    "ht-talented-long-term": "ht-foundation",
    "ht-student-aid": "ht-foundation",
    "cht-fang-hsien-chi": "cht-foundation",
    "heart-child": "ccft-foundation",
    "sunshine-scholarship": "sunshine-foundation",
    "sunshine-wanzu": "sunshine-foundation",
    "cfh-disabled-family": "cfh-foundation",
    "lovepeace-disadvantaged": "lovepeace-foundation",
    "dapeng-aid": "dapeng-foundation",
    "hndasset-wenxiang": "wenxiang-foundation",
    "cy-arch-aid": "cy-arch-foundation",
    "lihpao-fullon": "lihpao-foundation",
    "gfc-scholarship": "gfc-foundation",
    "auden-innovation-research": "auden-foundation",
    "auden-university-talent": "auden-foundation",
    "harmony-stability": "harmony-stability",
    "taishin-youth-volunteer": "taishin-charity",
}

_URL_TYPE_BY_ID = {
    "tf4dr-aid": SourceUrlType.LIST,
    "foxconn-scholarship-whale": SourceUrlType.EVERGREEN,
    "avc-talented-student": SourceUrlType.EVERGREEN,
    "cfh-graduate": SourceUrlType.LIST,
    "cfh-university": SourceUrlType.LIST,
    "kumota-flying": SourceUrlType.LIST,
    "lijin-taoyuan": SourceUrlType.LIST,
    "tcb-foundation": SourceUrlType.RELAY_LIST,
    "tainan-kaiji": SourceUrlType.RELAY_DETAIL,
    "songliang-aid": SourceUrlType.EVERGREEN,
    "wang-yun-wu-self-study": SourceUrlType.LIST,
    "rehe-association": SourceUrlType.RELAY_DETAIL,
    "wisdomshare-service-learning": SourceUrlType.EVERGREEN,
    "hsinrong-emergency-aid": SourceUrlType.RELAY_LIST,
    "it-social-care": SourceUrlType.RELAY_DETAIL,
    "you-care-hand-in-hand": SourceUrlType.LIST,
    "chiu-filial-piety": SourceUrlType.RELAY_LIST,
    "buddha-charity-progress": SourceUrlType.ANNUAL_DETAIL,
    "yonglin-hope": SourceUrlType.CORE_COVERED,
    "cdf-vocational": SourceUrlType.EVERGREEN,
    "ht-emergency": SourceUrlType.HOMEPAGE,
    "ht-talented-long-term": SourceUrlType.HOMEPAGE,
    "ht-student-aid": SourceUrlType.HOMEPAGE,
    "cht-fang-hsien-chi": SourceUrlType.EVERGREEN,
    "heart-child": SourceUrlType.EVERGREEN,
    "sunshine-scholarship": SourceUrlType.LIST,
    "sunshine-wanzu": SourceUrlType.LIST,
    "cfh-disabled-family": SourceUrlType.LIST,
    "lovepeace-disadvantaged": SourceUrlType.HOMEPAGE,
    "dapeng-aid": SourceUrlType.RELAY_DETAIL,
    "hndasset-wenxiang": SourceUrlType.CORE_COVERED,
    "cy-arch-aid": SourceUrlType.EVERGREEN,
    "lihpao-fullon": SourceUrlType.EVERGREEN,
    "gfc-scholarship": SourceUrlType.LIST,
    "auden-innovation-research": SourceUrlType.LIST,
    "auden-university-talent": SourceUrlType.LIST,
    "harmony-stability": SourceUrlType.RELAY_DETAIL,
    "taishin-youth-volunteer": SourceUrlType.HOMEPAGE,
}

# 只覆寫已核對的精準入口、正式轉載與核心來源。
_SOURCE_OVERRIDES: dict[str, tuple[str, str]] = {
    "foxconn-scholarship-whale": (
        "https://www.foxconnfoundation.org/plan/scholar/university",
        OFFICIAL_VERIFIED,
    ),
    "avc-talented-student": (
        "https://www.avcgroup.org/Scholar",
        OFFICIAL_VERIFIED,
    ),
    "kumota-flying": (
        "https://www.kumota.org/care/child-and-adolescent/",
        OFFICIAL_VERIFIED,
    ),
    "lijin-taoyuan": (
        "https://www.lijin.com.tw/Extend/Foundation/News",
        OFFICIAL_VERIFIED,
    ),
    "tcb-foundation": (
        "https://student.nutc.edu.tw/p/403-1020-34-1.php?Lang=zh-tw",
        SOURCE_RELAY,
    ),
    "wang-yun-wu-self-study": (
        "https://yunwu.org.tw/y/news/category/6",
        OFFICIAL_VERIFIED,
    ),
    "wisdomshare-service-learning": (
        "https://www.wisdomshare.com.tw/index.php?action=plan-detail&id=4",
        OFFICIAL_VERIFIED,
    ),
    "hsinrong-emergency-aid": (
        "https://osa.nfu.edu.tw/zh_tw/4/help",
        SOURCE_RELAY,
    ),
    "it-social-care": (
        "https://announce.yzu.edu.tw/index.php/tw/st/st-lgs20260521-1630-01",
        SOURCE_RELAY,
    ),
    "you-care-hand-in-hand": (
        "https://www.you-care.org.tw/List.aspx?mid=34",
        OFFICIAL_VERIFIED,
    ),
    "chiu-filial-piety": (
        "https://www.ymsh.tp.edu.tw/category/office/div_110/section_112/d1101_line/",
        SOURCE_RELAY,
    ),
    "buddha-charity-progress": (
        "https://www.buddha-charity.org/main.php?funName=news_content&id=114",
        OFFICIAL_VERIFIED,
    ),
    "cdf-vocational": (
        "https://www.cdffoundation.org/%E4%B8%AD%E8%8F%AF%E9%96%8B%E7%99%BC%E6%96%87%E6%95%99%E5%9F%BA%E9%87%91%E6%9C%83/%E4%B8%AD%E8%8F%AF%E9%96%8B%E7%99%BC%E6%8A%80%E8%97%9D%E8%81%B7%E8%83%BD%E7%8D%8E%E5%AD%B8%E9%87%91",
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
        "https://www.ccft.org.tw/OnePage.aspx?tid=128",
        OFFICIAL_VERIFIED,
    ),
    "cy-arch-aid": (
        "https://www.cy-arch.com.tw/foundation/scholarship",
        OFFICIAL_VERIFIED,
    ),
    "harmony-stability": (
        "https://www.hk.edu.tw/remote/HKlf_1238963/",
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
    "dapeng-aid": (
        "https://www.hn.thu.edu.tw/web/school/announcement.php?aid=12909&cid=4&department=15",
        SOURCE_RELAY,
    ),
    "yonglin-hope": ("", SOURCE_CORE),
    "hndasset-wenxiang": ("", SOURCE_CORE),
}

_FALLBACK_URLS = {
    "foxconn-scholarship-whale": ("https://www.foxconnfoundation.org/",),
    "avc-talented-student": ("https://www.avcgroup.org/",),
    "kumota-flying": (
        "https://www.kumota.org/",
        "https://www.kumota.org/care-detail/scholarship01__114/",
    ),
    "lijin-taoyuan": (
        "https://www.lijin.com.tw/Extend/Foundation/Application",
    ),
    "tcb-foundation": (
        "https://student.nutc.edu.tw/p/406-1020-117849%2Cr34.php?Lang=zh-tw",
    ),
    "wang-yun-wu-self-study": ("https://yunwu.org.tw/",),
    "wisdomshare-service-learning": (
        "https://www.wisdomshare.com.tw/index.php?action=plan",
        "https://www.wisdomshare.com.tw/",
    ),
    "hsinrong-emergency-aid": (
        "https://www.hsinrong.org/",
        "https://skjh.chc.edu.tw/posts/969",
    ),
    "it-social-care": ("https://itss.csroc.org.tw/",),
    "you-care-hand-in-hand": (
        "https://www.you-care.org.tw/",
        "https://www.you-care.org.tw/service/OnePage.aspx?id=1865&tid=133",
    ),
    "chiu-filial-piety": (
        "https://pyjh.chc.edu.tw/posts/1238",
        "https://skjh.chc.edu.tw/posts/970",
    ),
    "buddha-charity-progress": ("https://www.buddha-charity.org/",),
    "cdf-vocational": (
        "https://www.cdffoundation.org/scholarships",
        "https://www.cdffoundation.org/",
    ),
    "sunshine-scholarship": ("https://scholarship.sunshine.org.tw/",),
    "sunshine-wanzu": ("https://scholarship.sunshine.org.tw/",),
    "cy-arch-aid": ("https://www.cy-arch.com.tw/foundation",),
    "lihpao-fullon": ("https://www.lihpao.org.tw/active.php",),
    "auden-innovation-research": ("https://www.auden.com.tw/",),
    "auden-university-talent": ("https://www.auden.com.tw/",),
}

_RISK_BY_TYPE = {
    SourceUrlType.LIST: SourceRisk.LOW,
    SourceUrlType.EVERGREEN: SourceRisk.LOW,
    SourceUrlType.RELAY_LIST: SourceRisk.MEDIUM,
    SourceUrlType.HOMEPAGE: SourceRisk.MEDIUM,
    SourceUrlType.ANNUAL_DETAIL: SourceRisk.HIGH,
    SourceUrlType.RELAY_DETAIL: SourceRisk.HIGH,
    SourceUrlType.APPLICATION_PORTAL: SourceRisk.CRITICAL,
    SourceUrlType.CORE_COVERED: SourceRisk.LOW,
    SourceUrlType.PENDING: SourceRisk.CRITICAL,
    SourceUrlType.WRONG: SourceRisk.CRITICAL,
}

_EXPECTED_BY_TYPE = {
    SourceUrlType.LIST: "列表應持續出現新年度申請與結果公告。",
    SourceUrlType.EVERGREEN: "固定方案頁應更新年度辦法、期限或附件。",
    SourceUrlType.ANNUAL_DETAIL: "年度單篇可作本期正文，跨年度必須重新發現。",
    SourceUrlType.RELAY_LIST: "正式機構轉載列表應持續出現新年度公告。",
    SourceUrlType.RELAY_DETAIL: "年度轉載單篇可作本期正文，跨年度必須重新發現。",
    SourceUrlType.HOMEPAGE: "首頁必須二次發現方案頁或年度公告連結。",
    SourceUrlType.APPLICATION_PORTAL: "申請系統只可作送件入口，不得作公告發現來源。",
    SourceUrlType.CORE_COVERED: "由核心來源涵蓋，不重複請求。",
    SourceUrlType.PENDING: "尚未找到可靠入口。",
    SourceUrlType.WRONG: "入口與方案無關，禁止產生正式候選。",
}


# 合併 URL 與 fallback 的合法 host。
def _allowed_hosts(primary_url: str, fallbacks: tuple[str, ...]) -> tuple[str, ...]:
    hosts = {
        host
        for url in (primary_url, *fallbacks)
        if (host := urlparse(url).hostname)
    }
    return tuple(sorted(hosts))


# 將目錄項目與品質 metadata 合併為同一個可執行來源物件。
def _resolve(item: ScholarshipProgramWatch) -> ResolvedProgramSource:
    primary_url, status = _SOURCE_OVERRIDES.get(
        item.program_id,
        (item.official_url, item.official_status),
    )
    url_type = _URL_TYPE_BY_ID[item.program_id]
    fallbacks = _FALLBACK_URLS.get(item.program_id, tuple())
    return ResolvedProgramSource(
        item.program_id,
        item.title,
        item.organizer,
        item.aliases,
        primary_url,
        status,
        _ORGANIZER_IDS[item.program_id],
        url_type,
        _allowed_hosts(primary_url, fallbacks),
        f"{item.title}：{_EXPECTED_BY_TYPE[url_type]}",
        _RISK_BY_TYPE[url_type],
        fallbacks,
        VERIFIED_AT,
    )


# 回傳完成 URL 品質分類的 38 項方案。
def resolved_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(_resolve(item) for item in TUN_2025_PROGRAMS)


# 回傳本群組會直接下載的官方或正式機構轉載入口。
def monitorable_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(
        item
        for item in resolved_programs()
        if item.official_status in {OFFICIAL_VERIFIED, SOURCE_RELAY}
        and is_monitorable_url_type(item.source_url_type)
    )


# 回傳已由六核心來源涵蓋的方案。
def core_covered_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(
        item for item in resolved_programs() if item.official_status == SOURCE_CORE
    )


# 回傳沒有可靠入口或被品質模型阻擋的方案。
def unresolved_programs() -> tuple[ResolvedProgramSource, ...]:
    return tuple(
        item
        for item in resolved_programs()
        if item.official_status == SOURCE_PENDING
        or item.source_url_type in {SourceUrlType.PENDING, SourceUrlType.WRONG}
    )


# 驗證 URL host、類型與 38 項覆蓋完整性。
def validate_resolved_sources() -> None:
    catalog_ids = {item.program_id for item in TUN_2025_PROGRAMS}
    for mapping in (_ORGANIZER_IDS, _URL_TYPE_BY_ID):
        if set(mapping) != catalog_ids:
            raise ValueError("38 項來源品質 metadata 未完整覆蓋目錄")
    for item in resolved_programs():
        _validate_source(item)


# 驗證單一來源不會把登入、錯頁或不合法 host 當成正式入口。
def _validate_source(item: ResolvedProgramSource) -> None:
    if not item.organizer_id or not item.expected_discovery or not item.last_verified_at:
        raise ValueError(f"來源品質欄位不完整：{item.program_id}")
    if item.source_url_type in BLOCKED_URL_TYPES:
        if item.source_url_type == SourceUrlType.CORE_COVERED and item.official_url:
            raise ValueError(f"核心來源覆蓋不得重複請求：{item.program_id}")
        return
    if not item.official_url.startswith(("https://", "http://")):
        raise ValueError(f"可監測方案缺少網址：{item.program_id}")
    host = urlparse(item.official_url).hostname or ""
    if host not in item.allowed_hosts:
        raise ValueError(f"入口 host 未列入 allowed_hosts：{item.program_id}")


validate_resolved_sources()