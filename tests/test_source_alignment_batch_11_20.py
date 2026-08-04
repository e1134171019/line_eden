# -*- coding: utf-8 -*-

from dataclasses import replace

import pytest

from src.catalogs.tun_live_contracts import live_contract
from src.catalogs.tun_program_sources import ResolvedProgramSource, resolved_programs
from src.collectors.announcement_detail_fetcher import AnnouncementDetailFetcher
from src.collectors.evidence_detail_fetcher import EvidenceDetailFetcher
from src.collectors.resilient_tun_program_watch_collector import _source_variants
from src.diagnostics.detail_fetch_diagnostics import (
    DetailFetchResult,
    ResourceDiagnostic,
    RULES_STATUS_NOT_REQUIRED,
    RULES_STATUS_RESOLVED,
)
from src.matchers.program_name_matcher import match_program
from src.models.scholarship import Scholarship
from src.models.source_quality import SourceUrlType


def _source(program_id: str) -> ResolvedProgramSource:
    return next(item for item in resolved_programs() if item.program_id == program_id)


def _source_with_live_aliases(program_id: str) -> ResolvedProgramSource:
    source = _source(program_id)
    contract = live_contract(program_id)
    aliases = tuple(dict.fromkeys((*source.aliases, *contract.aliases)))
    return replace(source, aliases=aliases)


def _success_source(url: str, text: str) -> ResourceDiagnostic:
    return ResourceDiagnostic(
        role="source",
        requested_url=url,
        final_url=url,
        content_type="text/html",
        size_bytes=len(text.encode("utf-8")),
        document_kind="html",
        status="success",
        text_length=len(text),
    )


def test_wang_yun_wu_actual_list_title_is_source_scoped_alias() -> None:
    result = match_program(
        "114年獎學金申請",
        _source_with_live_aliases("wang-yun-wu-self-study"),
    )

    assert result.matched is True
    assert result.program_id == "wang-yun-wu-self-study"


def test_rehe_uses_cross_year_list_and_drops_old_catalog_detail() -> None:
    source = _source("rehe-association")
    contract = live_contract(source.program_id)

    variants = _source_variants(
        source,
        contract.preferred_sources,
        use_catalog_sources=contract.use_catalog_sources,
        current_year=2026,
    )

    assert contract.force_replace is True
    assert contract.use_catalog_sources is False
    assert variants[0].source_url_type is SourceUrlType.RELAY_LIST
    assert variants[0].url.endswith("/p/412-1034-63.php?Lang=zh-tw")
    assert all(item.url != source.official_url for item in variants)


def test_information_social_care_separates_discovery_and_rules_sources() -> None:
    source = _source("it-social-care")
    contract = live_contract(source.program_id)

    variants = _source_variants(
        source,
        contract.preferred_sources,
        use_catalog_sources=contract.use_catalog_sources,
        current_year=2026,
    )

    assert contract.force_replace is True
    assert contract.include_reference_evidence is True
    assert contract.use_catalog_sources is False
    assert variants[0].source_url_type is SourceUrlType.RELAY_DETAIL
    assert variants[1].source_url_type is SourceUrlType.RELAY_LIST
    assert contract.reference_sources[0].url == "https://itss.csroc.org.tw/about/"
    assert all(item.url != contract.reference_sources[0].url for item in variants)


def test_expired_2026_detail_is_removed_but_cross_year_list_remains() -> None:
    for program_id in (
        "it-social-care",
        "buddha-charity-progress",
        "yonglin-hope",
    ):
        source = _source(program_id)
        contract = live_contract(program_id)
        in_2026 = _source_variants(
            source,
            contract.preferred_sources,
            use_catalog_sources=contract.use_catalog_sources,
            current_year=2026,
        )
        in_2027 = _source_variants(
            source,
            contract.preferred_sources,
            use_catalog_sources=contract.use_catalog_sources,
            current_year=2027,
        )

        assert any(item.valid_through_year == 2026 for item in in_2026)
        assert all(item.valid_through_year is None for item in in_2027)
        assert any(
            item.source_url_type in {SourceUrlType.LIST, SourceUrlType.RELAY_LIST}
            for item in in_2027
        )


def test_buddha_charity_uses_official_list_for_cross_year_discovery() -> None:
    contract = live_contract("buddha-charity-progress")

    assert contract.force_replace is True
    assert contract.use_catalog_sources is False
    assert any(
        item.url == "https://www.buddha-charity.org/main.php?funName=news"
        and item.source_url_type is SourceUrlType.LIST
        for item in contract.preferred_sources
    )


def test_yonglin_evergreen_page_is_reference_not_announcement_candidate() -> None:
    source = _source("yonglin-hope")
    contract = live_contract(source.program_id)
    variants = _source_variants(
        source,
        contract.preferred_sources,
        use_catalog_sources=contract.use_catalog_sources,
        current_year=2027,
    )

    assert contract.use_catalog_sources is False
    assert contract.reference_sources[0].url.endswith("/project/education/detail/28")
    assert all(item.url != contract.reference_sources[0].url for item in variants)


def test_cdf_uses_new_canonical_evergreen_url() -> None:
    source = _source("cdf-vocational")
    contract = live_contract(source.program_id)
    variants = _source_variants(
        source,
        contract.preferred_sources,
        use_catalog_sources=contract.use_catalog_sources,
        current_year=2026,
    )

    assert contract.force_replace is True
    assert contract.use_catalog_sources is False
    assert variants[0].url == (
        "https://www.cdffoundation.org/zh-tw/scholarships/"
        "vocational-education-scholarship"
    )
    assert variants[0].source_url_type is SourceUrlType.EVERGREEN


def test_puren_new育成_title_matches() -> None:
    result = match_program(
        "2026大手拉小手—育成計畫",
        _source_with_live_aliases("you-care-hand-in-hand"),
    )

    assert result.matched is True
    assert result.program_id == "you-care-hand-in-hand"


def test_evidence_fetcher_appends_non_candidate_rules_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    annual_url = (
        "https://announce.yzu.edu.tw/index.php/tw/st/"
        "st-lgs20260521-1630-01"
    )
    rules_url = "https://itss.csroc.org.tw/about/"
    calls: list[str] = []

    def fake_fetch(
        _self: AnnouncementDetailFetcher,
        scholarship: Scholarship,
    ) -> DetailFetchResult:
        calls.append(scholarship.source_url)
        text = (
            "115年資訊人社會關懷獎學金申請公告"
            if scholarship.source_url == annual_url
            else "資訊人社會關懷獎學金設置辦法與固定申請資格"
        )
        return DetailFetchResult(
            text=text,
            source=_success_source(scholarship.source_url, text),
            attachments=tuple(),
            discovered_attachment_count=0,
            body_text=text,
            extracted_attachments=tuple(),
            rules_status=RULES_STATUS_NOT_REQUIRED,
        )

    monkeypatch.setattr(
        AnnouncementDetailFetcher,
        "fetch_with_diagnostics",
        fake_fetch,
    )
    scholarship = Scholarship.from_raw(
        "tun-program-it-social-care",
        "資訊人社會關懷獎學金",
        "2026-05-21",
        annual_url,
        program_id="it-social-care",
        detail_url=annual_url,
    )
    fetcher = EvidenceDetailFetcher(1, "test-agent", 2, 1024 * 1024, 10)

    result = fetcher.fetch_with_diagnostics(scholarship)

    assert calls == [annual_url, rules_url]
    assert result.rules_status == RULES_STATUS_RESOLVED
    assert "固定申請資格" in result.text
    assert result.extracted_attachments[-1].content_role == "scholarship_rules"
