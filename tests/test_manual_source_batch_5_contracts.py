# -*- coding: utf-8 -*-

from src.catalogs.tun_2025_program_catalog import OFFICIAL_VERIFIED
from src.catalogs.tun_program_sources import (
    SOURCE_RELAY,
    ResolvedProgramSource,
    resolved_programs,
)
from src.models.source_quality import SourceRisk, SourceUrlType


# 以 program_id 取得人工核對後的來源契約。
def _sources() -> dict[str, ResolvedProgramSource]:
    return {item.program_id: item for item in resolved_programs()}


# 最後七項必須指向精準方案、辦法或正式轉載頁。
def test_manual_batch_5_source_types_and_urls() -> None:
    sources = _sources()

    dapeng = sources["dapeng-aid"]
    assert dapeng.official_status == SOURCE_RELAY
    assert dapeng.source_url_type == SourceUrlType.RELAY_DETAIL
    assert "nfuosa.nfu.edu.tw" in dapeng.official_url
    assert dapeng.update_risk == SourceRisk.HIGH

    wenxiang = sources["hndasset-wenxiang"]
    assert wenxiang.official_status == OFFICIAL_VERIFIED
    assert wenxiang.source_url_type == SourceUrlType.EVERGREEN
    assert wenxiang.official_url == "https://www.hndasset.com/csr/"

    cy_arch = sources["cy-arch-aid"]
    assert cy_arch.official_status == OFFICIAL_VERIFIED
    assert cy_arch.source_url_type == SourceUrlType.EVERGREEN
    assert cy_arch.official_url.endswith("/foundation/scholarship")

    lihpao = sources["lihpao-fullon"]
    assert lihpao.official_status == OFFICIAL_VERIFIED
    assert lihpao.source_url_type == SourceUrlType.EVERGREEN
    assert lihpao.official_url.endswith("active_detail.php?no=95")

    auden = sources["auden-innovation-research"]
    assert auden.official_status == OFFICIAL_VERIFIED
    assert auden.source_url_type == SourceUrlType.LIST
    assert "https://www.auden.com.tw/2025innovation/" in auden.fallback_urls

    harmony = sources["harmony-stability"]
    assert harmony.official_status == OFFICIAL_VERIFIED
    assert harmony.source_url_type == SourceUrlType.ANNUAL_DETAIL
    assert harmony.official_url == "https://rsd.fashui.org/archives/33101"
    assert harmony.update_risk == SourceRisk.HIGH

    taishin = sources["taishin-youth-volunteer"]
    assert taishin.official_status == OFFICIAL_VERIFIED
    assert taishin.source_url_type == SourceUrlType.EVERGREEN
    assert taishin.official_url == "https://www.taishinyouth.org.tw/apply2.php"


# 主入口與 fallback 的所有 host 都必須列入 allowlist。
def test_manual_batch_5_allowed_hosts_cover_fallbacks() -> None:
    sources = _sources()
    expected_hosts = {
        "dapeng-aid": {
            "nfuosa.nfu.edu.tw",
            "www.edu.tw",
            "www.hn.thu.edu.tw",
        },
        "hndasset-wenxiang": {"www.hndasset.com", "assistance.ncnu.edu.tw"},
        "cy-arch-aid": {"www.cy-arch.com.tw"},
        "lihpao-fullon": {"www.lihpao.org.tw"},
        "auden-innovation-research": {"www.auden.com.tw"},
        "harmony-stability": {"rsd.fashui.org", "www.hk.edu.tw"},
        "taishin-youth-volunteer": {"www.taishinyouth.org.tw"},
    }

    for program_id, hosts in expected_hosts.items():
        assert set(sources[program_id].allowed_hosts) == hosts