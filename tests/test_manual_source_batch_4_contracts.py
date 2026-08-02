# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import OFFICIAL_VERIFIED
from src.catalogs.tun_program_sources import ResolvedProgramSource, resolved_programs
from src.models.source_quality import SourceRisk, SourceUrlType


# 以 program_id 取得人工核對後的來源契約。
def _sources() -> dict[str, ResolvedProgramSource]:
    return {item.program_id: item for item in resolved_programs()}


# 第四批七個來源必須使用實際辦法、申請書或官方列表，不得停在首頁。
def test_manual_batch_4_source_types_and_urls() -> None:
    sources = _sources()

    yonglin = sources["yonglin-hope"]
    assert yonglin.official_status == OFFICIAL_VERIFIED
    assert yonglin.source_url_type == SourceUrlType.EVERGREEN
    assert yonglin.official_url.endswith("/project/education/detail/28")

    emergency = sources["ht-emergency"]
    assert emergency.official_status == OFFICIAL_VERIFIED
    assert emergency.source_url_type == SourceUrlType.EVERGREEN
    assert emergency.official_url.endswith("/p1_religion_5_24.htm")

    talented = sources["ht-talented-long-term"]
    assert talented.official_status == OFFICIAL_VERIFIED
    assert talented.source_url_type == SourceUrlType.EVERGREEN
    assert talented.official_url.endswith("/religion178.htm")

    student_aid = sources["ht-student-aid"]
    assert student_aid.official_status == OFFICIAL_VERIFIED
    assert student_aid.source_url_type == SourceUrlType.EVERGREEN
    assert student_aid.official_url.endswith("/religion154.htm")

    sunshine = sources["sunshine-wanzu"]
    assert sunshine.official_status == OFFICIAL_VERIFIED
    assert sunshine.source_url_type == SourceUrlType.LIST
    assert sunshine.official_url == "https://scholarship.sunshine.org.tw/?cat=1"

    cfh_family = sources["cfh-disabled-family"]
    assert cfh_family.official_status == OFFICIAL_VERIFIED
    assert cfh_family.source_url_type == SourceUrlType.LIST
    assert cfh_family.official_url == "https://www.cfh.org.tw/?cat=9"

    lovepeace = sources["lovepeace-disadvantaged"]
    assert lovepeace.official_status == OFFICIAL_VERIFIED
    assert lovepeace.source_url_type == SourceUrlType.LIST
    assert lovepeace.official_url.startswith("https://www.lovepeace.org.tw/Download.php")
    assert lovepeace.update_risk == SourceRisk.LOW


# 主入口與 fallback 的 host 必須全部列入 allowlist。
def test_manual_batch_4_allowed_hosts_cover_fallbacks() -> None:
    sources = _sources()
    expected_hosts = {
        "yonglin-hope": {"www.yonglin.org.tw"},
        "ht-emergency": {"www.ht.org.tw"},
        "ht-talented-long-term": {"www.ht.org.tw"},
        "ht-student-aid": {"www.ht.org.tw"},
        "sunshine-wanzu": {"scholarship.sunshine.org.tw"},
        "cfh-disabled-family": {"www.cfh.org.tw"},
        "lovepeace-disadvantaged": {
            "www.lovepeace.org.tw",
            "service.utaipei.edu.tw",
        },
    }

    for program_id, hosts in expected_hosts.items():
        assert set(sources[program_id].allowed_hosts) == hosts