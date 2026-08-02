# -*- coding: utf-8 -*-

from enum import StrEnum


class SourceUrlType(StrEnum):
    """來源 URL 對長期公告發現能力的分類。"""

    LIST = "url_list"
    EVERGREEN = "url_evergreen"
    ANNUAL_DETAIL = "url_annual_detail"
    RELAY_LIST = "url_relay_list"
    RELAY_DETAIL = "url_relay_detail"
    HOMEPAGE = "url_homepage"
    APPLICATION_PORTAL = "url_application_portal"
    CORE_COVERED = "url_core_covered"
    PENDING = "url_pending"
    WRONG = "url_wrong"


class SourceRisk(StrEnum):
    """來源跨年度維護風險。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


MONITORABLE_URL_TYPES = frozenset(
    {
        SourceUrlType.LIST,
        SourceUrlType.EVERGREEN,
        SourceUrlType.ANNUAL_DETAIL,
        SourceUrlType.RELAY_LIST,
        SourceUrlType.RELAY_DETAIL,
        SourceUrlType.HOMEPAGE,
    }
)
DIRECT_CANDIDATE_URL_TYPES = frozenset(
    {
        SourceUrlType.EVERGREEN,
        SourceUrlType.ANNUAL_DETAIL,
        SourceUrlType.RELAY_DETAIL,
    }
)
BLOCKED_URL_TYPES = frozenset(
    {
        SourceUrlType.APPLICATION_PORTAL,
        SourceUrlType.CORE_COVERED,
        SourceUrlType.PENDING,
        SourceUrlType.WRONG,
    }
)


# 判斷來源是否可由 TUN collector 直接請求。
def is_monitorable_url_type(url_type: SourceUrlType) -> bool:
    return url_type in MONITORABLE_URL_TYPES


# 判斷沒有日期與獨立連結時，入口頁本身能否作為候選正文。
def allows_direct_candidate(url_type: SourceUrlType) -> bool:
    return url_type in DIRECT_CANDIDATE_URL_TYPES
