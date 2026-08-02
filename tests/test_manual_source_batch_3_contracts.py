# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import OFFICIAL_VERIFIED
from src.catalogs.tun_program_sources import SOURCE_RELAY, resolved_programs
from src.models.source_quality import SourceRisk, SourceUrlType


# 以 program_id 取得人工核對後的來源契約。
def _sources() -> dict[str, object]:
    return {item.program_id: item for item in resolved_programs()}


# 固定方案頁、官方列表、年度單篇與正式轉載不得互相混用。
def test_manual_batch_3_source_types_and_urls() -> None:
    sources = _sources()

    wisdomshare = sources["wisdomshare-service-learning"]
    assert wisdomshare.official_status == OFFICIAL_VERIFIED
    assert wisdomshare.source_url_type == SourceUrlType.EVERGREEN
    assert wisdomshare.official_url.endswith("action=plan-detail&id=4")
    assert wisdomshare.update_risk == SourceRisk.LOW

    hsinrong = sources["hsinrong-emergency-aid"]
    assert hsinrong.official_status == SOURCE_RELAY
    assert hsinrong.source_url_type == SourceUrlType.RELAY_LIST
    assert hsinrong.official_url == "https://osa.nfu.edu.tw/zh_tw/4/help"
    assert "https://www.hsinrong.org/" in hsinrong.fallback_urls

    information = sources["it-social-care"]
    assert information.official_status == SOURCE_RELAY
    assert information.source_url_type == SourceUrlType.RELAY_DETAIL
    assert information.official_url.startswith("https://announce.yzu.edu.tw/")
    assert information.update_risk == SourceRisk.HIGH

    puren = sources["you-care-hand-in-hand"]
    assert puren.official_status == OFFICIAL_VERIFIED
    assert puren.source_url_type == SourceUrlType.LIST
    assert puren.official_url == "https://www.you-care.org.tw/List.aspx?mid=34"

    chiu = sources["chiu-filial-piety"]
    assert chiu.official_status == SOURCE_RELAY
    assert chiu.source_url_type == SourceUrlType.RELAY_LIST
    assert chiu.official_url.startswith("https://www.ymsh.tp.edu.tw/category/")

    buddha = sources["buddha-charity-progress"]
    assert buddha.official_status == OFFICIAL_VERIFIED
    assert buddha.source_url_type == SourceUrlType.ANNUAL_DETAIL
    assert buddha.official_url.endswith("funName=news_content&id=114")
    assert buddha.update_risk == SourceRisk.HIGH

    cdf = sources["cdf-vocational"]
    assert cdf.official_status == OFFICIAL_VERIFIED
    assert cdf.source_url_type == SourceUrlType.EVERGREEN
    assert cdf.official_url.startswith("https://www.cdffoundation.org/")
    assert "https://www.cdffoundation.org/scholarships" in cdf.fallback_urls


# 主入口與 fallback 的所有 host 都必須列入 allowlist。
def test_manual_batch_3_allowed_hosts_cover_fallbacks() -> None:
    sources = _sources()
    expected_hosts = {
        "wisdomshare-service-learning": {"www.wisdomshare.com.tw"},
        "hsinrong-emergency-aid": {
            "osa.nfu.edu.tw",
            "www.hsinrong.org",
            "skjh.chc.edu.tw",
        },
        "it-social-care": {"announce.yzu.edu.tw", "itss.csroc.org.tw"},
        "you-care-hand-in-hand": {"www.you-care.org.tw"},
        "chiu-filial-piety": {
            "www.ymsh.tp.edu.tw",
            "pyjh.chc.edu.tw",
            "skjh.chc.edu.tw",
        },
        "buddha-charity-progress": {"www.buddha-charity.org"},
        "cdf-vocational": {"www.cdffoundation.org"},
    }

    for program_id, hosts in expected_hosts.items():
        assert set(sources[program_id].allowed_hosts) == hosts